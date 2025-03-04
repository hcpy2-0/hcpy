## [0.4.2] - 2025-03-04
## What's Changed
* Fix parsing step where it is a float instead of an integer
* Revert use of step to indicate a writeable number value
* Add IDos to discovery.yaml as numbers


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.4.0...v0.4.2
## [0.4.1] - 2025-03-03
## What's Changed
* Allow discovery.yaml configuration by user by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/153


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.4.0...v0.4.1b
## [0.4.0] - 2025-02-28
## Breaking

Moved to one topic per device attribute. This greatly reduces the complexity of any value_template, but does mean that manually configured entities will need to be updated. Any auto discovered entities should pickup the new settings.  

The new state topics will be in the format `/homeconnect/device_name/state/entity_name` e.g. `/homeconnect/refrigerator/state/bsh_common_status_doorstate` . The value is pushed direct to this topic with no JSON so will contained just `Closed` or `Open` in this example. 

I hope this is the last big change regarding the formatting and publishing of data as this provides a good level of coverage for most features in the device through the discovery mechanism.  Enough for me to remove my manually configured MQTT settings. 

## What's Changed
* Remove programs from HADiscovery by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/147
* Use native python TLS-PSK by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/123
* Return none when value not found by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/146 


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.3.0...v0.4.0
## [0.3.0] - 2025-02-21
## What's Changed
* Login update - remove redundant email/password arguments by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/143
* Discovery - Naming and initValue improvements by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/135

Breaking Changes:
This release adds a lot of functionality to the HA Discovery mechanism to create switches, buttons, numbers, select entities of controllable items, as well as the ability to select a basic ActiveProgram. This will redefine a lot of existing entities that are sensors/binary_sensors to usable types. Would suggest the use of MQTTExplorer to delete the trees under homeassistant/select/hcpy and binary_sensors to clear up old entities (although they may well still work). 

The discovery.yaml is not currently user configurable outside of the docker container, but should provide an easy way to override entity properties in the discovery to share configurations. 

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.2.3...v0.3.0
## [0.2.3] - 2025-02-13
## What's Changed
* Fix payload off typo by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/137


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.2.2...v0.2.3
## [0.2.2] - 2025-02-03
## What's Changed
* Update README.md by @lapodomo in https://github.com/hcpy2-0/hcpy/pull/126
* Revert removal of features being stored in devices.json by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/132

## New Contributors
* @lapodomo made their first contribution in https://github.com/hcpy2-0/hcpy/pull/126

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.2.1...v0.2.2

Many changes in v0.2.0 many of which will break existing sensors and automations so please check before/when upgrading. 
## [0.2.1] - 2025-01-31
Please check breaking changes from v0.2.0!

## What's Changed
* Add Add-on link to Readme by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/124
* Fix stderr print by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/125


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.2.0...v0.2.1


## [0.2.0] - 2025-01-31
## What's Changed
* BREAKING: Use fully qualified names for attributes by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/109


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.8...v0.2.0

Previously we relied on the final section of an entity (e.g. `DoorState` within `BSH.Common.Status.DoorState`) to be unique, but this is not the case across a number of devices, therefore we have changed the naming convention to use the fully qualified entity name. This will break existing MQTT configurations and change auto discovered instances, so please review all configurations.

The AutoDiscovery also made modifications to devices.json but this is no longer a very viable approach as the login process has become more complex after having CAPTCHAs introduced. 

Autodiscovery also treated many entities as binary_sensors (e.g. a door), however HomeConnect may have several different states for a door such as Open, Closed, Ajar. We treat these entities as sensor with a device_class of enum now. 

Events are no longer passed as sensors, but now will be registered as events by Autodiscovery.
## [0.1.8] - 2025-01-30
## What's Changed
* Change hc-login due to hcaptcha by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/117


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.7...v0.1.8
## [0.1.7] - 2025-01-30
## What's Changed
* Fix MQTT reconnection exception  - when dynamic features are added to a device name may not be set by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/121
* Flush print all log messages by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/122


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.6...v0.1.7
## [Resolves nested enums] - 2024-12-16
## What's Changed
* Small readme fixes for docker-compose commands by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/106
* fix: Resolve every enum there is in the xml blobs by @Hypfer in https://github.com/hcpy2-0/hcpy/pull/105

## New Contributors
* @Hypfer made their first contribution in https://github.com/hcpy2-0/hcpy/pull/105

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.5...v0.1.6
## [0.1.5] - 2024-10-07
## What's Changed
* Execute hc login on first run by @saveriol in https://github.com/hcpy2-0/hcpy/pull/95
* Release Version v0.1.5 by @pmagyar in https://github.com/hcpy2-0/hcpy/pull/98


**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.4...v0.1.5

## Note
If you use the Homeassistant Addon you have to fill out the HCPY_HOMECONNECT_EMAIL and HCPY_HOMECONNECT_PASSWORD configuration settings. 
## [0.1.4] - 2024-09-25
## What's Changed
* Revert host to name in mqtt topic by @saveriol in https://github.com/hcpy2-0/hcpy/pull/93
* addon version v0.1.4 by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/94

## New Contributors
* @saveriol made their first contribution in https://github.com/hcpy2-0/hcpy/pull/93

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.3...v0.1.4
## [0.1.3] - 2024-08-19
## What's Changed
* [pre-commit.ci] pre-commit autoupdate by @pre-commit-ci in https://github.com/hcpy2-0/hcpy/pull/85
* Add Home Assistant MQTT autodiscovery by @jamesremuscat in https://github.com/hcpy2-0/hcpy/pull/86
* addon version v0.1.3 by @pmagyar in https://github.com/hcpy2-0/hcpy/pull/87

## New Contributors
* @jamesremuscat made their first contribution in https://github.com/hcpy2-0/hcpy/pull/86

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.2...v0.1.3
## [0.1.2] - 2024-07-21
## What's Changed
* New feature: selecting program by @Dis90 in https://github.com/hcpy2-0/hcpy/pull/83

## New Contributors
* @Dis90 made their first contribution in https://github.com/hcpy2-0/hcpy/pull/83

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.1...v0.1.2
## [0.1.1] - 2024-05-14
## What's Changed
* Fix incorrect path to hc-login.py in readme example by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/63
* [pre-commit.ci] pre-commit autoupdate by @pre-commit-ci in https://github.com/hcpy2-0/hcpy/pull/65
* Process description changes by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/62
* Retain per device online LWT messages by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/66
* Login: Support for North America by @axxapy in https://github.com/hcpy2-0/hcpy/pull/68
* Add debug options by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/70
* Add domain_suffix option by @Meatballs1 in https://github.com/hcpy2-0/hcpy/pull/71

## New Contributors
* @axxapy made their first contribution in https://github.com/hcpy2-0/hcpy/pull/68

**Full Changelog**: https://github.com/hcpy2-0/hcpy/compare/v0.1.0...v0.1.1
## [0.1.0] - 2024-04-20
Home Assisstant Add-On
