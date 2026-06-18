#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
ADB="${ADB:-$SDK_DIR/platform-tools/adb}"

if [ ! -x "$ADB" ]; then
    echo "missing adb: $ADB" >&2
    exit 1
fi

APK=$("$ROOT_DIR/build_apk.sh")

"$ADB" reverse tcp:44353 tcp:4353
"$ADB" reverse tcp:44354 tcp:4354
"$ADB" install -r "$APK"
"$ADB" shell am start -n pl.kigo.xcvario.bridge/.MainActivity

echo "installed: $APK"
echo "Kigo/Nav on phone: 127.0.0.1:4353, FLARM 127.0.0.1:4354"
