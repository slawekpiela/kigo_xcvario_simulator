# Kigo Android Bridge APK

Small Android helper APK for feeding the simulator into Kigo/Nav on a phone
connected to the Mac with USB debugging.

## Data Path

```text
Kigo/Nav on Android
  tcp_client 127.0.0.1:4353 / 4354
        |
Android Bridge APK
  listens on 127.0.0.1:4353 / 4354
  connects to 127.0.0.1:44353 / 44354
        |
adb reverse
  device tcp:44353 -> Mac tcp:4353
  device tcp:44354 -> Mac tcp:4354
        |
Kigo XCVario simulator on the Mac
```

The APK is a local TCP bridge. It does not emulate an Android serial device;
Android does not let a normal APK expose a virtual serial port to another APK.

## Build

The project intentionally avoids Gradle because this repository already has no
Android build system. It uses the local Android SDK tools directly:

```bash
./android_bridge/build_apk.sh
```

Requirements:

- Android SDK under `ANDROID_HOME`, `ANDROID_SDK_ROOT`, or
  `$HOME/Library/Android/sdk`,
- JDK/JBR under `JAVA_HOME`, Android Studio, or PyCharm.

The signed debug APK is written to:

```text
android_bridge/build/kigo-android-bridge.apk
```

## Install

Start the simulator so the Mac has local TCP listeners on `4353` and `4354`,
then connect the phone over USB with Android debugging enabled:

```bash
./android_bridge/install_bridge.sh
```

That script:

- builds the APK,
- installs it with `adb install -r`,
- creates the required `adb reverse` mappings,
- opens the bridge screen.

The bridge does not autostart. Press `Start` in the bridge app when you want
the foreground bridge service running, and press `Stop` before leaving it idle.
The service is not exported to other Android apps. The main screen shows clear
`Connected` and `Transmitting` indicators above the raw per-channel counters:

- `Connected: YES` means both local Kigo/Nav sockets are bridged to the Mac
  upstream ports; `PARTIAL` means only one channel is bridged.
- `Transmitting: YES` means bridge bytes flowed recently; `PARTIAL` means only
  one channel is currently moving data.

If the simulator runs on a VM instead of the Mac, first expose the VM simulator
ports on the Mac as local `4353` and `4354` before running the install script.

## Kigo/Nav Device Settings

Primary device:

```text
DeviceA="XCVario"
PortType="tcp_client"
PortIPAddress="127.0.0.1"
PortTCPPort="4353"
```

FLARM:

```text
DeviceB="FLARM"
Port2Type="tcp_client"
Port2IPAddress="127.0.0.1"
Port2TCPPort="4354"
```

For SxHAWK, keep port `4353` but use the matching LX/LXNAV device driver in
Kigo/Nav.

## Troubleshooting

If Kigo/Nav still reports a connection error, check the active Android profile.
On Android 11 devices observed here, Kigo loads:

```text
/sdcard/Android/media/kigo.nav/XCSoarData/kigo_default.top
```

Older copies under `/sdcard/Android/data/kigo.nav/files/XCSoarData` can be
stale. The active profile must use `tcp_client` with empty serial paths:

```text
PortType="tcp_client"
PortIPAddress="127.0.0.1"
PortPath=""
PortTCPPort="4353"

Port3Type="tcp_client"
Port3IPAddress="127.0.0.1"
Port3Path=""
Port3TCPPort="4354"
```
