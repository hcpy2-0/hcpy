# Home Assistant

For integration with Home Assistant, the following MQTT examples can be used to create entities:

## Coffee Machine

```yaml
- unique_id: "coffee_machine"
  name: "Coffee Machine"
  state_topic: "homeconnect/coffeemaker/state"
  value_template: "{{ value_json.PowerState }}"
  json_attributes_topic: "homeconnect/coffeemaker/state"
  json_attributes_template: "{{ value_json | tojson }}"
```

## Extractor Fan

```yaml
fan:
  - name: "Hood"
    state_topic: "homeconnect/hood/state"
    state_value_template: "{{ value_json.PowerState }}"
    command_topic: "homeconnect/hood/set"
    command_template: "{{ iif(value == 'On', '{\"uid\":539,\"value\":2}', '{\"uid\":539,\"value\":1}') }}"
    payload_on: "On"
    payload_off: "Off"
light:
  - name: "Hood Work Light" # We can only turn the light on, but not off as no command_template
    state_topic: "homeconnect/hood/state"
    state_value_template: "{{ value_json.Lighting }}"
    brightness_state_topic: "homeconnect/hood/state"
    brightness_value_template: "{{ value_json.LightingBrightness }}"
    brightness_command_topic: "homeconnect/hood/set"
    brightness_command_template: "{{ '{\"uid\":53254,\"value\":' + value|string + '}'  }}"
    brightness_scale: 100
    command_topic: "homeconnect/hood/set"
    on_command_type: brightness
    #command_template: "{{ iif(value == 'on', '{\"uid\":53253,\"value\":true}', '{\"uid\":53253,\"value\":false}') }}" WIP - MQTT doesn't allow this to be configured
    payload_on: true
    payload_off: false
```

## Refrigerator/Freezers

```yaml
binary_sensor:
  - name: "Freezer Door"
    state_topic: "homeconnect/freezer/state"
    value_template: "{{ value_json.Freezer }}"
    payload_on: "Open"
    payload_off: "Closed"
    device_class: door
    json_attributes_topic: "homeconnect/freezer/state"
  - name: "Fridge Door"
    state_topic: "homeconnect/refrigerator/state"
    value_template: "{{ value_json.DoorState }}" # Also Refrigerator
    payload_on: "Open"
    payload_off: "Closed"
    device_class: door
    json_attributes_topic: "homeconnect/refrigerator/state"
```

## Dishwasher

```yaml
  - name: "Dishwasher"
    state_topic: "homeconnect/dishwasher/state"
    value_template: "{{ value_json.PowerState }}"
    payload_on: "On"
    payload_off: "Off"
    json_attributes_topic: "homeconnect/dishwasher/state"
  - name: "Dishwasher Door"
    state_topic: "homeconnect/dishwasher/state"
    value_template: "{{ value_json.DoorState }}"
    payload_on: "Open"
    payload_off: "Closed"
    device_class: door
```

