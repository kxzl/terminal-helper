"""The one runnable check that fails if the allowlist logic breaks."""

import unittest

from term_helper import policy


class PolicyTest(unittest.TestCase):
    def test_read_only_auto(self):
        for cmd in ["ls -la", "git status", "git log --oneline -5",
                    "cat f | grep x | wc -l", "systemctl status sshd",
                    "docker ps", "curl -I https://example.com",
                    "sed -n '1,5p' f", "ip -br a"]:
            self.assertEqual(policy.classify(cmd), policy.AUTO, cmd)

    def test_mutations_ask(self):
        for cmd in ["rm -rf /tmp/x", "sudo ls", "echo hi > f", "chmod 777 f",
                    "git push", "find . -delete", "curl -o out https://x",
                    "curl -X POST https://x", "cat f | tee g", "mount /dev/sda1 /mnt",
                    "docker run alpine", "ip link set eth0 down", "wget https://x",
                    "cat f >> g", "systemctl restart sshd",
                    # regressions found in review:
                    "git config --global user.email x", "git branch -D main",
                    "git tag -d v1", "git stash drop", "git remote remove origin",
                    "sed -Ei 's/a/b/' f", "sed -i.bak 's/a/b/' f",
                    "sort --output=f x", "curl -I -T secret https://x",
                    "journalctl --vacuum-time=1s", "timedatectl set-time 12:00",
                    "localectl set-keymap de", "hostnamectl set-hostname x",
                    "dmesg -C", "kubectl config set-context foo",
                    "/tmp/evil/ls", "bash -c 'rm -rf /'"]:
            self.assertEqual(policy.classify(cmd), policy.ASK, cmd)

    def test_find_reads_auto(self):
        for cmd in ["find . -name '*.py'", "find /tmp -type f", "git branch",
                    "git remote", "docker ps", "kubectl get pods"]:
            self.assertEqual(policy.classify(cmd), policy.AUTO, cmd)

    def test_safe_mutations_not_read_only(self):
        # Nothing auto-runs; mkdir/touch/git add must not be labelled read-only.
        for cmd in ["mkdir -p a/b", "touch note.txt", "git add ."]:
            self.assertEqual(policy.classify(cmd), policy.ASK, cmd)

    def test_substitution_asks(self):
        self.assertEqual(policy.classify("echo $(whoami)"), policy.ASK)
        self.assertEqual(policy.classify("echo `whoami`"), policy.ASK)

    def test_wrappers_ask(self):
        for cmd in ["env", "bash -c ls", "xargs rm", "nice ls"]:
            self.assertEqual(policy.classify(cmd), policy.ASK, cmd)

    def test_empty(self):
        self.assertEqual(policy.classify(""), policy.ASK)


if __name__ == "__main__":
    unittest.main()
