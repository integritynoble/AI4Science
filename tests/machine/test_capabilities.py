from ai4science.harness.agents.machine.capabilities import detect_machine


def _fake(system, machine, present=()):
    return dict(system=lambda: system, machine=lambda: machine,
                which=lambda t: ("/usr/bin/" + t) if t in present else None)


def test_detects_linux_and_installed_tools():
    caps = detect_machine(**_fake("Linux", "x86_64", present=("git", "node")))
    assert caps["os"] == "linux" and caps["arch"] == "x86_64" and caps["supported"] is True
    assert caps["installed"]["git"] is True and caps["installed"]["claude"] is False


def test_detects_macos_arm64():
    caps = detect_machine(**_fake("Darwin", "arm64", present=("claude",)))
    assert caps["os"] == "macos" and caps["arch"] == "arm64"
    assert caps["installed"]["claude"] is True


def test_detects_windows():
    caps = detect_machine(**_fake("Windows", "AMD64"))
    assert caps["os"] == "windows" and caps["arch"] == "x86_64" and caps["supported"] is True


def test_unknown_os_is_unsupported():
    caps = detect_machine(**_fake("Plan9", "x86_64"))
    assert caps["supported"] is False
