# Local experiment's minimal ARM device selection.
# This upstream revision unconditionally links its GICv5 CPU-interface helpers.
# Supply their device-side symbols; no GICv5 device is instantiated by devemu.
CONFIG_ARM_GICV5=y
CONFIG_P2D_DEVEMU=y
CONFIG_P2D_NE2000=y
