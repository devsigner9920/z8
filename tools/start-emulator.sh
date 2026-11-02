#!/bin/sh
# Android 17/API 37 ARM64, 16 KB page-size development emulator (not hardware).
# Installs only with --install; APK installation is deliberately separate.
set -eu
z8_tools_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
z8_root_dir=$(dirname -- "$z8_tools_dir")
z8_local="$z8_root_dir/.local"
export JAVA_HOME="$z8_local/jdk/Contents/Home"
export ANDROID_HOME="$z8_local/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_USER_HOME="$z8_local/android-user"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
export ANDROID_EMULATOR_HOME="$ANDROID_USER_HOME/emulator"
export JAVA_TOOL_OPTIONS="-Duser.home=$ANDROID_USER_HOME"
z8_image='system-images;android-37.0;google_apis_ps16k;arm64-v8a'
z8_image_dir="$ANDROID_HOME/system-images/android-37.0/google_apis_ps16k/arm64-v8a"
z8_avd=z8-api37-arm64-16k
z8_port=${Z8_EMULATOR_PORT:-5580}
z8_install=false
z8_prepare_only=false
z8_windowed=false

for z8_arg in "$@"; do
    case "$z8_arg" in
        --install) z8_install=true ;;
        --prepare-only) z8_prepare_only=true ;;
        --windowed) z8_windowed=true ;;
        --help|-h)
            printf '%s\n' 'Usage: tools/start-emulator.sh [--install] [--prepare-only] [--windowed]' \
                'Starts a project-local Android 17/API 37 ARM64 16 KB emulator (headless by default).' \
                'Uses the Pixel Fold hardware profile with 4096 MB emulated RAM.' \
                'This is an emulator, not Galaxy Fold hardware or an 8 GB RAM acceptance test.' \
                '--install explicitly downloads missing SDK emulator and image packages.' \
                '--prepare-only creates the AVD without starting it.' \
                '--windowed opens the emulator window for interactive use.' \
                'Z8_EMULATOR_PORT defaults to 5580; adb serial is emulator-5580.' \
                'The foreground emulator exits on Ctrl-C; no APK is installed.'
            exit 0 ;;
        *) printf 'Unknown option: %s\n' "$z8_arg" >&2; exit 2 ;;
    esac
done

case "$z8_port" in
    [0-9][0-9][0-9][0-9]) ;;
    *) printf '%s\n' 'Z8_EMULATOR_PORT must be an even port from 5554 to 5682.' >&2; exit 2 ;;
esac
if [ "$z8_port" -lt 5554 ] || [ "$z8_port" -gt 5682 ] || [ $((z8_port % 2)) -ne 0 ]; then
    printf '%s\n' 'Z8_EMULATOR_PORT must be an even port from 5554 to 5682.' >&2
    exit 2
fi
if [ ! -x "$JAVA_HOME/bin/java" ]; then
    printf '%s\n' 'Missing project-local JDK. Complete tools/setup-toolchain.py first.' >&2
    exit 2
fi
mkdir -p "$ANDROID_USER_HOME" "$ANDROID_AVD_HOME" "$ANDROID_EMULATOR_HOME"
if "$z8_install"; then
    "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" "--sdk_root=$ANDROID_HOME" emulator "$z8_image"
fi
if [ ! -x "$ANDROID_HOME/emulator/emulator" ] || [ ! -f "$z8_image_dir/package.xml" ]; then
    printf '%s\n' 'Emulator/image not installed. Run tools/start-emulator.sh --install.' >&2
    exit 2
fi
if [ ! -f "$ANDROID_AVD_HOME/$z8_avd.ini" ]; then
    printf 'no\n' | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager" create avd \
        --name "$z8_avd" --package "$z8_image" --device pixel_fold \
        --path "$ANDROID_AVD_HOME/$z8_avd.avd"
fi
printf 'EMULATOR ONLY: API 37 / ARM64 / expected 16 KB pages; AVD=%s; serial=emulator-%s\n' "$z8_avd" "$z8_port"
if "$z8_prepare_only"; then
    exit 0
fi
# Local config/key-store paths are explicit; no root or system image writes.
# The OS hypervisor remains in control. No software-acceleration fallback hides failure.
set -- -avd "$z8_avd" -port "$z8_port" \
    -no-audio -no-boot-anim -no-snapshot -no-metrics \
    -crash-report-mode disabled -memory 4096 -cores 2 -gpu swiftshader
if ! "$z8_windowed"; then
    set -- "$@" -no-window
fi
exec "$ANDROID_HOME/emulator/emulator" "$@"
