"""Exact app-owned English/Korean labels for the dedicated-emulator probes.

Keep fixture names, commands and protocol values out of this table. Matching is
exact (or an explicit accessibility prefix); it must never authorize a different
action just because its wording looks similar.
"""

LABELS = {
    'settings': ('Settings', '환경설정', '터미널 메뉴'),  # Last value: historical APK.
    'diagnostics': ('Runtime diagnostics', '런타임 진단', '실행 진단'),
    'environment': ('Current project environment', '현재 프로젝트 환경', '개발 환경'),
    'start_theme': ('Start with this theme', '이 테마로 시작'),
    'setup_environment': ('Set up environment', '개발 환경 준비'),
    'tools_ready': ('Linux installed · Tools ready', 'Linux 설치됨 · 개발 도구 준비됨'),
    'tools_needed': ('Linux installed · Tools need setup', 'Linux 설치됨 · 개발 도구 준비 필요'),
    'tools_delayed': ('Linux installed · Some tool checks delayed', 'Linux 설치됨 · 일부 도구 확인 지연'),
    'open_terminal': ('Open new terminal', '새 터미널 열기'),
    'diagnostic_shell': ('New Android diagnostic shell', '새 Android 진단 셸 만들기'),
    'install_runtime': ('Install Linux runtime / Open terminal', 'Linux 런타임 설치 / 터미널 열기'),
    'open_runtime': ('Open Linux runtime terminal', 'Linux 런타임 터미널 열기'),
    'projects': ('Projects and sessions', '프로젝트와 세션 목록'),
    'rename': ('Rename', '이름 변경'),
    'save': ('Save', '저장'),
    'close_terminal': ('Close terminal…', '터미널 종료…'),
    'cancel': ('Cancel', '취소'),
    'close_session': ('Close session', '세션 종료'),
    'remove_from_list': ('Remove from list', '목록에서 제거'),
    'remove': ('Remove', '제거'),
    'select_project': ('Select project: {project}', '프로젝트 선택: {project}'),
    'new_session': ('{project}: new session', '{project}에 새 세션'),
    'expanded_project': ('Project sessions: {project} · Expanded', '프로젝트 세션 목록: {project} · 펼침'),
    'switch_prefix': ('Switch session: ', '세션 전환: '),
    'select_prefix': ('Select session: ', '세션 선택: '),
    'switch_session': ('Switch session: {project} / {title} / ', '세션 전환: {project} / {title} / '),
    'switch_project': ('Switch session: {project} / ', '세션 전환: {project} / '),
    'select_session': ('Select session: {project} / {title} / ', '세션 선택: {project} / {title} / '),
    'ended_session': ('Select session: {project} / {title} / Ended', '세션 선택: {project} / {title} / 종료됨'),
    # Rejection-only labels from the removed chooser; never used to select it.
    'chooser': ('Project for new session', '새 세션의 프로젝트'),
    'project_chooser': ('{project} · New session', '{project} · 새 세션'),
    'tool_chooser': ('Choose a tool for this project.', '이 프로젝트에서 사용할 도구를 선택하세요.'),
}


def labels(key, **values):
    return tuple(label.format(**values) for label in LABELS[key])


def matches(actual, expected):
    """Only explicit tuples accept alternatives; ordinary fixture strings stay exact."""
    return actual in expected if isinstance(expected, tuple) else actual == expected


def strip_prefix(value, prefixes):
    for prefix in prefixes:
        if value.startswith(prefix):
            return value[len(prefix):]
    return None


def collapsed_project(description):
    return any(description.startswith(prefix) and description.endswith(suffix)
               and len(description) > len(prefix) + len(suffix)
               for prefix, suffix in (('Project sessions: ', ' · Collapsed'),
                                      ('프로젝트 세션 목록: ', ' · 접힘')))
