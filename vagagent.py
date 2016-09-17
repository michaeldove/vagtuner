import struct
import array
import can
from can import Message

####################################
# Addressing
####################################
TESTER_CAN_ID = 0x200
ECU_LOGICAL_ADDRESS = 0x01
MY_VWTP_CAN_ID = 0x740
####################################
# KWP ECU Identification
####################################
# Opcodes
KWP_READ_ECU_IDENTIFICATION_OPCODE = 0x1a
KWP_READ_ECU_IDENTIFICATION_RESP_OPCODE = 0x5a
# Parameters
KWP_EXTENDED_ECU_IDENT_PARAM = 0x86
KWP_ITEM_NUMBER_PARAM = 0x9b
KWP_IMMO_PARAM = 0x92
KWP_SOFTWARE_VERSION_PARAM = 0x95
KWP_ENGINE_TYPE_PARAM = 0x97
KWP_VIN_PARAM = 0x90
####################################
# VWTP
####################################
SETUP_REQUEST_OPCODE = 0xc0
SETUP_RESPONSE_OPCODE = 0xd0
VWTP_OPCODE_LAST_PACKET_ACK = 0x1
VWTP_OPCODE_MORE_PACKETS_NOACK = 0x2
CAN_ID_INVALID_MASK = 0x10
VWTP_PAYLOAD_INDEX = 3
VWTP_FRAME_LENGTH = 8
VWTP_FRAME_HEADER_LENGTH = 1
VWTP_FRAME_HEADER_FIRST_LENGTH = 3
KWP2000_APP_TYPE = 0x01

####################################
# Variables
####################################
can_interface = 'vcan0'
dest_vwtp_can_id = 0x0
vag_part_number = '8P0907115AQ'
engine = '2.0l R4/4V TFSI'


class KWP2000Message(object):
    def __init__(self, opcode, param, data):
        self.opcode = opcode
        self.param = param
        self.data = data
    
    def bytes(self):
        return bytearray([self.opcode, self.param]) + self.data

class VWTP2(object):
    """VW Transport Protocol 2.0"""

    def __init__(self, bus):
        self.bus = bus
        self.seq = 0

    def can_handle_message(self, can_message):
        return can_message.arbitration_id == MY_VWTP_CAN_ID

    def handle_message(self, can_message):
        """Handle VWTP frame"""
        # we're a VWTP session
        vwtp_opcode = data[0] >> 4
        vwtp_seq = data[0] & 0xf
        if vwtp_opcode == VWTP_OPCODE_LAST_PACKET_ACK:
            # Act on packet and respond with ack
            vwtp_next_seq = (vwtp_seq + 1) & 0xf
            self.send_ack(vwtp_next_seq)
        if vwtp_seq == 0:
            payload_len = data[2] # refactor this to a intermessage context
            # What if payload length is greater than message size?
            # Should add message payload to a read buffer and send to a app
            # protocol handler once transfer is complete.
            kwp_payload = data[VWTP_PAYLOAD_INDEX:VWTP_PAYLOAD_INDEX+payload_len]
            kwp_opcode = kwp_payload[0]
            kwp_param = kwp_payload[1]
            if kwp_opcode == KWP_READ_ECU_IDENTIFICATION_OPCODE:
                if kwp_param == KWP_ITEM_NUMBER_PARAM:
                    send_item_number(tp)

    def send(self, message):
        payload_start_index = 0
        payload = message.bytes()
        message_length = len(payload)
        remaining_length = message_length

        while remaining_length:
            vwtp_header_length = VWTP_FRAME_HEADER_LENGTH
            first_frame = self.seq == 0
            if first_frame:
                vwtp_header_length = VWTP_FRAME_HEADER_FIRST_LENGTH
            vwtp_payload_length = VWTP_FRAME_LENGTH - vwtp_header_length
            last_frame = vwtp_payload_length >= remaining_length

            opcode = VWTP_OPCODE_MORE_PACKETS_NOACK
            if last_frame:
                opcode = VWTP_OPCODE_LAST_PACKET_ACK
            first_byte = opcode << 4 | self.seq

            data = bytearray([first_byte])
            if first_frame:
                data += bytearray([0x00, message_length])

            payload_end_index = payload_start_index + vwtp_payload_length
            frame_payload_bytes = payload[payload_start_index:payload_end_index]
            data += frame_payload_bytes

            message = Message(extended_id=False,
                              arbitration_id=dest_vwtp_can_id,
                              data=data)
            self.bus.send(message)
            remaining_length -= len(frame_payload_bytes)
            payload_start_index += len(frame_payload_bytes)
            self.seq = (self.seq + 1) & 0xf

    def send_ack(self, seq):
        message = Message(extended_id=False,
        arbitration_id=dest_vwtp_can_id,
        data=[0xb0 + seq])
        self.bus.send(message)

def send_item_number(tp):
    # length = 46
    data = bytearray(46)
    values = ["{:<11}".format(vag_part_number),
        0x20,0x30,0x30,0x31,0x30,0x10,0x00,
        0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,
        "{:<20}".format(engine)]
    struct.pack_into('11sBBBBBBBBBBBBBBB20s', data, 0, *values)
    message = KWP2000Message(
        KWP_READ_ECU_IDENTIFICATION_RESP_OPCODE,
        KWP_ITEM_NUMBER_PARAM,
        data)
    tp.send(message)
          


bus = can.interface.Bus(can_interface, bustype='socketcan')
tp = VWTP2(bus)
for message in bus:
    msg_can_id = message.arbitration_id
    data = message.data
    if msg_can_id == TESTER_CAN_ID:
        # we're in raw can frame mode with a tester connected
        if data[0] == ECU_LOGICAL_ADDRESS:
            # OK, the tester is talking to us (ECU)
            if data[1] == SETUP_REQUEST_OPCODE:
                dest_vwtp_can_id_invalid = data[5] & CAN_ID_INVALID_MASK
                if dest_vwtp_can_id_invalid:
                    print "Error: Invalid destination VWTP CAN ID."
                    continue
            dest_vwtp_can_id = struct.unpack('<H', data[4:6])[0]
            if data[6] != KWP2000_APP_TYPE:
                print "Error: Expecting KWP2000 app type."
                continue
            response_data = [0x00, 
                             SETUP_RESPONSE_OPCODE, 
                             dest_vwtp_can_id & 0xff, 
                             dest_vwtp_can_id >> 8, 
                             MY_VWTP_CAN_ID & 0xff, 
                             MY_VWTP_CAN_ID >> 8,
                             KWP2000_APP_TYPE]
            message = Message(extended_id=False,
                              arbitration_id=TESTER_CAN_ID+1,
                              data=response_data) 
            bus.send(message)
            continue
    if tp.can_handle_message(message):
        tp.handle_message(message)
