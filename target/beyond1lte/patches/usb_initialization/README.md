# Galaxy S10 legacy USB initialization

The vendor `sec_charging` configuration includes the MTP FunctionFS function.
Init can attempt to bind it before system_server opens the MTP control endpoint.
The bind then fails, but the vendor action still publishes `sys.usb.state`.
Consequently, equal config/state properties do not prove that this initial
configuration was applied successfully.

This services.jar patch invalidates that initial applied flag only in the
normal/unknown boot-mode branch of the legacy handler initialization, when
the configuration is exactly `sec_charging` and `nativeOpenControl("mtp")`
has returned a non-null descriptor. The next existing function update uses
the normal `none` → requested configuration sequence and state acknowledgments.
Successful application sets the flag again through the existing handler.

Other initial configurations, special boot modes, the gadget HAL handler and
subsequent connection handling retain their existing behavior. The patch does
not enable ADB or file access, change notification conditions, or perform
periodic resets. It is packaged only for beyond1lte.

After rebuilding, validate USB-debugging-OFF startup both with and without a
PC connected, USB mode changes and file transfers, ordinary charging,
ADB ON/OFF, and OTG/DeX/HDMI role transitions. DEX assembly validation alone
does not establish successful runtime initialization or device compatibility.
