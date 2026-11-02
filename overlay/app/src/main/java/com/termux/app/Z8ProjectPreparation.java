package com.termux.app;

import android.content.Context;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.Collections;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicBoolean;

/** Blocking preparation for the service's worker. No Activity, dialog or temporary terminal. */
public final class Z8ProjectPreparation {
    interface Progress { void update(String stage, int percent, String message); }
    private static final int LOG_LIMIT = 16000;
    private Z8ProjectPreparation() {}

    static void run(Context context, String id, Progress progress) throws Exception {
        run(context, id, progress, Collections.emptyMap());
    }

    static void run(Context context, String id, Progress progress, Map<String, String> downloadEnvironment) throws Exception {
        Z8EnvironmentTemplate.project(context, id);
        progress.update("bootstrap", -1, "실행 기반 준비");
        Z8Bootstrap.ensure(context, (percent, message) -> progress.update("bootstrap", percent, "실행 기반 준비"));
        progress.update("rootfs", -1, Z8EnvironmentTemplate.isTemplate(id) ? "Linux 환경 준비" : "프로젝트 환경 준비");
        Z8Guest.ensureRootfs(context, id, (percent, message) -> progress.update("rootfs", percent, message));
        if (Z8Guest.standardProfilePrepared(context, id)) return;
        progress.update("tools", -1, "개발 도구 설치");
        Z8Guest.Launch launch = Z8Guest.actionCommand(context, id, null, "setup-tools");
        List<String> arguments = new ArrayList<>(Arrays.asList(launch.arguments));
        List<String> assignments = new ArrayList<>();
        for (Map.Entry<String, String> entry : downloadEnvironment.entrySet()) {
            if (!Arrays.asList("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy", "NO_PROXY").contains(entry.getKey())
                    || entry.getValue() == null || entry.getValue().indexOf('\0') >= 0)
                throw new IOException("설치 연결 설정이 올바르지 않습니다.");
            assignments.add(entry.getKey() + "=" + entry.getValue());
        }
        // Assignments go to the guest's /usr/bin/env as argv, never through shell interpolation.
        arguments.addAll(launch.commandOffset, assignments);
        List<String> argv = new ArrayList<>(); argv.add(launch.executable); argv.addAll(arguments);
        Map<String, String> environment = new HashMap<>();
        environment.put("PATH", "/system/bin");
        environment.put("PROOT_TMP_DIR", context.getCacheDir().getAbsolutePath());
        Z8PreparationProcess process = Z8PreparationProcess.start(context, id, argv, new File(launch.workingDirectory), environment);
        StringBuilder tail = new StringBuilder();
        AtomicReference<IOException> readFailure = new AtomicReference<>();
        AtomicBoolean acceptingProgress = new AtomicBoolean(true);
        Thread reader = new Thread(() -> {
            try (InputStreamReader input = new InputStreamReader(process.output(), StandardCharsets.UTF_8)) {
                char[] buffer = new char[2048]; StringBuilder line = new StringBuilder(); boolean overflow = false;
                int count;
                while ((count = input.read(buffer)) != -1) {
                    synchronized (tail) {
                        tail.append(buffer, 0, count);
                        if (tail.length() > LOG_LIMIT) tail.delete(0, tail.length() - LOG_LIMIT);
                    }
                    for (int i = 0; i < count; i++) {
                        char value = buffer[i];
                        if (value == '\n') {
                            if (!overflow && acceptingProgress.get()) switch (line.toString()) {
                                case "Z8_SETUP:packages": progress.update("tools", -1, "Python · Git · 개발 도구 설치"); break;
                                case "Z8_SETUP:node": progress.update("tools", -1, "Node.js · npm 설치"); break;
                                case "Z8_SETUP:verify": progress.update("tools", -1, "설치 확인"); break;
                            }
                            line.setLength(0); overflow = false;
                        } else if (!overflow) {
                            if (line.length() < 256) line.append(value); else overflow = true;
                        }
                    }
                }
            } catch (IOException error) { readFailure.set(error); }
            catch (RuntimeException cancelled) { readFailure.set(new IOException("설치 진행 확인이 중단되었습니다.", cancelled)); }
        }, "z8-setup-output");
        reader.setDaemon(true); reader.start();
        try {
            if (!process.waitFor(30, TimeUnit.MINUTES)) throw new IOException("설치 시간이 초과되었습니다. 네트워크를 확인하고 다시 시도해 주세요.");
            reader.join(2000);
            if (reader.isAlive() || readFailure.get() != null) throw new IOException("설치 결과를 읽지 못했습니다. 다시 시도해 주세요.");
            if (process.exitValue() != 0 || !Z8Guest.standardProfilePrepared(context, id)) {
                String detail;
                synchronized (tail) { detail = tail.toString(); }
                for (String value : downloadEnvironment.values())
                    if (!value.isEmpty()) detail = detail.replace(value, "[설치 연결]");
                throw new IOException("개발 도구 설치가 완료되지 않았습니다 (" + process.exitValue()
                    + "). 네트워크와 저장 공간을 확인한 뒤 다시 시도해 주세요.\n\n" + detail);
            }
            Z8Guest.invalidateReadiness(id);
        } finally {
            acceptingProgress.set(false);
            // Verify SIGQUIT has drained the owned PRoot tree before another installer can run.
            process.close();
        }
    }
}
