#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_DIR="$ROOT_DIR/app"
BUILD_DIR="$ROOT_DIR/build"
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
PLATFORM_JAR="$SDK_DIR/platforms/android-36/android.jar"
JDK_HOME="${JAVA_HOME:-}"

if [ -z "$JDK_HOME" ]; then
    for candidate in \
        "/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
        "/Applications/PyCharm.app/Contents/jbr/Contents/Home"; do
        if [ -x "$candidate/bin/javac" ]; then
            JDK_HOME="$candidate"
            break
        fi
    done
fi
if [ -z "$JDK_HOME" ] || [ ! -x "$JDK_HOME/bin/javac" ]; then
    echo "missing JDK; set JAVA_HOME or install Android Studio/PyCharm JBR" >&2
    exit 1
fi
JAVA_BIN="$JDK_HOME/bin/java"
JAVAC_BIN="$JDK_HOME/bin/javac"
KEYTOOL_BIN="$JDK_HOME/bin/keytool"
export JAVA_HOME="$JDK_HOME"
PATH="$JDK_HOME/bin:$PATH"
export PATH

BUILD_TOOLS_DIR="${ANDROID_BUILD_TOOLS:-}"
if [ -z "$BUILD_TOOLS_DIR" ]; then
    for candidate in "$SDK_DIR"/build-tools/*; do
        case "$candidate" in
            *rc*) continue ;;
        esac
        BUILD_TOOLS_DIR="$candidate"
    done
fi
if [ -z "$BUILD_TOOLS_DIR" ]; then
    for candidate in "$SDK_DIR"/build-tools/*; do
        BUILD_TOOLS_DIR="$candidate"
    done
fi

AAPT2="$BUILD_TOOLS_DIR/aapt2"
D8="$BUILD_TOOLS_DIR/d8"
ZIPALIGN="$BUILD_TOOLS_DIR/zipalign"
APKSIGNER="$BUILD_TOOLS_DIR/apksigner"

for tool in "$AAPT2" "$D8" "$ZIPALIGN" "$APKSIGNER" "$JAVA_BIN" "$JAVAC_BIN" "$KEYTOOL_BIN" /usr/bin/zip; do
    if [ ! -x "$tool" ]; then
        echo "missing executable: $tool" >&2
        exit 1
    fi
done
if [ ! -f "$PLATFORM_JAR" ]; then
    echo "missing Android platform jar: $PLATFORM_JAR" >&2
    exit 1
fi

INTERMEDIATES_DIR="$BUILD_DIR/intermediates"
RES_ZIP="$INTERMEDIATES_DIR/resources.zip"
GEN_DIR="$INTERMEDIATES_DIR/generated"
CLASSES_DIR="$INTERMEDIATES_DIR/classes"
DEX_DIR="$INTERMEDIATES_DIR/dex"
UNALIGNED_APK="$INTERMEDIATES_DIR/kigo-android-bridge-unaligned.apk"
ALIGNED_APK="$INTERMEDIATES_DIR/kigo-android-bridge-aligned.apk"
FINAL_APK="$BUILD_DIR/kigo-android-bridge.apk"
KEYSTORE="$BUILD_DIR/debug.keystore"

rm -rf "$INTERMEDIATES_DIR"
mkdir -p "$GEN_DIR" "$CLASSES_DIR" "$DEX_DIR" "$BUILD_DIR"

if [ ! -f "$KEYSTORE" ]; then
    "$KEYTOOL_BIN" -genkeypair \
        -keystore "$KEYSTORE" \
        -storepass android \
        -alias androiddebugkey \
        -keypass android \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US" >&2
fi

"$AAPT2" compile --dir "$APP_DIR/src/main/res" -o "$RES_ZIP" >&2
"$AAPT2" link \
    -I "$PLATFORM_JAR" \
    --manifest "$APP_DIR/src/main/AndroidManifest.xml" \
    --java "$GEN_DIR" \
    --min-sdk-version 23 \
    --target-sdk-version 28 \
    --version-code 1 \
    --version-name 0.1.0 \
    -o "$UNALIGNED_APK" \
    "$RES_ZIP" >&2

"$JAVAC_BIN" \
    -source 1.8 \
    -target 1.8 \
    -bootclasspath "$PLATFORM_JAR" \
    -classpath "$GEN_DIR" \
    -d "$CLASSES_DIR" \
    $(find "$GEN_DIR" "$APP_DIR/src/main/java" -name '*.java') >&2

"$D8" --min-api 23 --lib "$PLATFORM_JAR" --output "$DEX_DIR" $(find "$CLASSES_DIR" -name '*.class') >&2
/usr/bin/zip -q -j "$UNALIGNED_APK" "$DEX_DIR/classes.dex" >&2
"$ZIPALIGN" -f -p 4 "$UNALIGNED_APK" "$ALIGNED_APK" >&2
"$APKSIGNER" sign \
    --ks "$KEYSTORE" \
    --ks-key-alias androiddebugkey \
    --ks-pass pass:android \
    --key-pass pass:android \
    --out "$FINAL_APK" \
    "$ALIGNED_APK" >&2
"$APKSIGNER" verify "$FINAL_APK" >&2

echo "$FINAL_APK"
