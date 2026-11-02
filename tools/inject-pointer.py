#!/usr/bin/env python3
"""Inject explicit SOURCE_MOUSE events into the foreground z8 emulator window.

Unlike adb's generic swipe this supplies real buttonState and Shift metadata.
Synthetic event coverage does not establish Bluetooth/USB hardware compatibility.
Requires known screen coordinates from a fresh capture; never guesses targets.
Does not install/restart the app, type commands, or read its clipboard.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['click', 'drag', 'middle-drag', 'right', 'scroll', 'hover'])
    parser.add_argument('x', type=int)
    parser.add_argument('y', type=int)
    parser.add_argument('--end-x', type=int)
    parser.add_argument('--end-y', type=int)
    parser.add_argument('--shift', action='store_true')
    parser.add_argument('--scroll', type=float, default=-1)
    args = parser.parse_args()
    adb = ROOT / '.local/android-sdk/platform-tools/adb'
    target = [str(adb), '-s', 'emulator-5580']
    def query(*words):
        return subprocess.check_output([*target, *words], text=True, timeout=30).strip()
    if query('shell', 'getprop', 'ro.kernel.qemu') != '1' or query('emu', 'avd', 'name').splitlines()[0] != 'z8-api37-arm64-16k':
        raise SystemExit('Refusing to inject outside the dedicated z8 emulator')
    window = query('shell', 'dumpsys', 'window')
    focus = [line for line in window.splitlines() if 'mCurrentFocus=' in line]
    if not any('dev.devsigner.z8/' in line for line in focus):
        raise SystemExit('z8 must be the foreground window')
    local = ROOT / '.local'
    jdk = local / 'jdk/Contents/Home'
    sdk = local / 'android-sdk'
    environment = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / 'bin') + os.pathsep + os.environ.get('PATH', ''))
    with tempfile.TemporaryDirectory(prefix='z8-pointer-') as temp:
        directory = Path(temp)
        source = directory / 'Z8PointerProbe.java'
        source.write_text(SOURCE)
        classes = directory / 'classes'; classes.mkdir()
        subprocess.run([str(jdk / 'bin/javac'), '-source', '8', '-target', '8', '-classpath', str(sdk / 'platforms/android-36/android.jar'), '-d', str(classes), str(source)], check=True, env=environment, capture_output=True)
        jar = directory / 'input.jar'
        with zipfile.ZipFile(jar, 'w') as archive:
            for item in classes.rglob('*.class'):
                archive.write(item, item.relative_to(classes))
        dex = directory / 'dex'; dex.mkdir()
        subprocess.run([str(sdk / 'build-tools/36.0.0/d8'), '--min-api', '28', '--lib', str(sdk / 'platforms/android-36/android.jar'), '--output', str(dex), str(jar)], check=True, env=environment, capture_output=True)
        package = directory / 'probe.jar'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.write(dex / 'classes.dex', 'classes.dex')
        remote = '/data/local/tmp/z8-pointer-probe.jar'
        subprocess.run([*target, 'push', str(package), remote], check=True, capture_output=True)
        try:
            command = ['app_process', '/system/bin', 'Z8PointerProbe', args.action, str(args.x), str(args.y),
                       str(args.end_x if args.end_x is not None else args.x),
                       str(args.end_y if args.end_y is not None else args.y), '1' if args.shift else '0', str(args.scroll)]
            print(query('shell', 'CLASSPATH=' + remote + ' ' + shlex.join(command)))
        finally:
            query('shell', 'rm', '-f', remote)


SOURCE = r'''import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.KeyEvent;
import android.view.MotionEvent;
import java.lang.reflect.Method;

public final class Z8PointerProbe {
    private static Object manager;
    private static Method inject;
    static void send(int action, float x, float y, int button, int meta, long start, float wheel) throws Exception {
        MotionEvent.PointerProperties properties = new MotionEvent.PointerProperties();
        properties.id = 0; properties.toolType = MotionEvent.TOOL_TYPE_MOUSE;
        MotionEvent.PointerCoords coordinates = new MotionEvent.PointerCoords();
        coordinates.x = x; coordinates.y = y; coordinates.pressure = button == 0 ? 0 : 1;
        coordinates.setAxisValue(MotionEvent.AXIS_VSCROLL, wheel);
        MotionEvent event = MotionEvent.obtain(start, SystemClock.uptimeMillis(), action, 1,
            new MotionEvent.PointerProperties[]{properties}, new MotionEvent.PointerCoords[]{coordinates},
            meta, button, 1, 1, 0, 0, InputDevice.SOURCE_MOUSE, 0);
        try {
            Method display = InputEvent.class.getDeclaredMethod("setDisplayId", int.class);
            display.invoke(event, 0);
            if (!Boolean.TRUE.equals(inject.invoke(manager, event, 2))) throw new IllegalStateException("Injection rejected");
        } finally { event.recycle(); }
    }
    public static void main(String[] args) throws Exception {
        Class<?> type;
        try { type = Class.forName("android.hardware.input.InputManagerGlobal"); }
        catch (ClassNotFoundException older) { type = Class.forName("android.hardware.input.InputManager"); }
        manager = type.getDeclaredMethod("getInstance").invoke(null);
        inject = type.getMethod("injectInputEvent", InputEvent.class, int.class);
        String action = args[0];
        float x = Float.parseFloat(args[1]), y = Float.parseFloat(args[2]);
        float endX = Float.parseFloat(args[3]), endY = Float.parseFloat(args[4]);
        int meta = "1".equals(args[5]) ? KeyEvent.META_SHIFT_ON | KeyEvent.META_SHIFT_LEFT_ON : 0;
        int button = "middle-drag".equals(action) ? MotionEvent.BUTTON_TERTIARY
            : "right".equals(action) ? MotionEvent.BUTTON_SECONDARY : MotionEvent.BUTTON_PRIMARY;
        long start = SystemClock.uptimeMillis();
        if ("scroll".equals(action)) send(MotionEvent.ACTION_SCROLL, x, y, 0, meta, start, Float.parseFloat(args[6]));
        else if ("hover".equals(action)) {
            send(MotionEvent.ACTION_HOVER_ENTER, x, y, 0, meta, start, 0);
            send(MotionEvent.ACTION_HOVER_MOVE, endX, endY, 0, meta, start, 0);
        } else {
            send(MotionEvent.ACTION_DOWN, x, y, button, meta, start, 0);
            if (action.endsWith("drag")) for (int i = 1; i <= 12; i++) {
                Thread.sleep(24);
                send(MotionEvent.ACTION_MOVE, x + (endX - x) * i / 12, y + (endY - y) * i / 12, button, meta, start, 0);
            }
            send(MotionEvent.ACTION_UP, endX, endY, 0, meta, start, 0);
        }
        System.out.println("PASS injected SOURCE_MOUSE " + action + (meta == 0 ? "" : " Shift"));
    }
}
'''

if __name__ == '__main__':
    main()
