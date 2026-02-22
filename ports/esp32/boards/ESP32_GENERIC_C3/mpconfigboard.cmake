set(IDF_TARGET esp32c3)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.riscv
    boards/sdkconfig.ble
    boards/ESP32_GENERIC_C3/sdkconfig.c3usb
    boards/sdkconfig.ble_wifi_coex
)
