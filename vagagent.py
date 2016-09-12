import struct
import array
import can
from can import Message

can_interface = 'vcan0'
tester_can_id = 0x200
ecu_logical_address = 0x01
setup_request_opcode = 0xc0
setup_response_opcode = 0xd0
can_id_invalid_mask = 0x10
my_vwtp_can_id = 0x740
dest_vwtp_can_id = 0x0
kwp2000_app_type = 0x01
vwtp_opcode_last_packet_ack = 0x1
vwtp_opcode_more_packets_noack = 0x2

####################################
# KWP ECU Identification
####################################
kwp_read_ecu_identification_opcode = 0x1a
kwp_read_ecu_identification_resp_opcode = 0x5a
kwp_extended_ecu_ident_param = 0x86
kwp_item_number_param = 0x9b
kwp_immo_param = 0x92
kwp_software_version_param = 0x95
kwp_engine_type_param = 0x97
kwp_vin_param = 0x90
####################################

vwtp_first_preamble_length = 3
vwtp_consecutive_preamble_length = 1
vwtp_payload_index = 3
max_frame_length = 8
ecu_id = "A1234567890"

def send_item_number(bus):
  payload = ecu_id
  payload_len = len(payload)
  remaining_len = payload_len
  seq = 0
  payload_index = 0
  while remaining_len:
    available_payload_space = None
    first_frame = seq == 0
    if first_frame:
      available_payload_space = max_frame_length - vwtp_first_preamble_length
    else:
      available_payload_space = max_frame_length - vwtp_consecutive_preamble_length
    payload_end_index = min(payload_index + remaining_len, payload_index + available_payload_space)
    last_frame = available_payload_space >= remaining_len
    opcode = vwtp_opcode_more_packets_noack
    if last_frame:
      opcode = vwtp_opcode_last_packet_ack
    first_byte = opcode << 4 | seq
    data = None

    frame_payload = payload[payload_index:payload_end_index]
    frame_payload_bytes = list(array.array('B', frame_payload))
    if first_frame:
      data = [first_byte, 0x00, payload_len, kwp_read_ecu_identification_resp_opcode, kwp_item_number_param] + frame_payload_bytes
    else:
      data = [first_byte] + frame_payload_bytes
    message = Message(extended_id=False,
                      arbitration_id=dest_vwtp_can_id,
                      data=data)
    bus.send(message)
    remaining_len = remaining_len - len(frame_payload)
    seq = seq+1


    

bus = can.interface.Bus(can_interface, bustype='socketcan')
for message in bus:
  msg_can_id = message.arbitration_id
  data = message.data
  if msg_can_id == tester_can_id:
    # we're in raw can frame mode with a tester connected
    if data[0] == ecu_logical_address:
      # OK, the tester is talking to us (ECU)
      if data[1] == setup_request_opcode:
        dest_vwtp_can_id_invalid = data[5] & can_id_invalid_mask
        if dest_vwtp_can_id_invalid:
          print "Error: Invalid destination VWTP CAN ID."
          continue
        dest_vwtp_can_id = struct.unpack('<H', data[4:6])[0]
        if data[6] != kwp2000_app_type:
          print "Error: Expecting KWP2000 app type."
          continue
        response_data = [0x00, 
                         setup_response_opcode, 
                         dest_vwtp_can_id & 0xff, 
                         dest_vwtp_can_id >> 8, 
                         my_vwtp_can_id & 0xff, 
                         my_vwtp_can_id >> 8,
                         kwp2000_app_type]
        message = Message(extended_id=False,
                          arbitration_id=tester_can_id+1,
                          data=response_data) 
        bus.send(message)
        continue
  if msg_can_id == my_vwtp_can_id:
    # we're a VWTP session
    vwtp_opcode = data[0] >> 4
    vwtp_seq = data[0] & 0xf
    if vwtp_opcode == vwtp_opcode_last_packet_ack:
      # Act on packet and respond with ack
      vwtp_next_seq = (vwtp_seq + 1) & 0xf
      message = Message(extended_id=False,
                        arbitration_id=dest_vwtp_can_id,
                        data=[0xb0 + vwtp_next_seq])
      bus.send(message)
      if vwtp_seq == 0:
        payload_len = data[2] # refactor this to a intermessage context
        kwp_payload = data[vwtp_payload_index:vwtp_payload_index+payload_len]
        kwp_opcode = kwp_payload[0]
        kwp_param = kwp_payload[1]
        if kwp_opcode == kwp_read_ecu_identification_opcode:
          if kwp_param == kwp_item_number_param:
            send_item_number(bus)
  print message

