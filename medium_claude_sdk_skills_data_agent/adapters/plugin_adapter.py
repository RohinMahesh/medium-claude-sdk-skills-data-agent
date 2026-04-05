import shutil
from dataclasses import dataclass, field
from pathlib import Path

from medium_claude_sdk_skills_data_agent.core.ports import PluginSyncPort


@dataclass
class PluginSync(PluginSyncPort):
    """
    Syncs Claude Code plugins from the plugins/ directory into the .claude/
    directory structure expected by the Claude Agent SDK at application startup.

    Writes:
        .claude/skills/<skill-name>/   <- from plugins/<plugin>/skills/<name>/
        .claude/commands/<name>.md     <- from plugins/<plugin>/commands/<name>.md

    :param plugins_root: the path to the plugins root folder
    :param claude_dir: the path to the .claude working directory
    :param synced_skills_dirs: paths of all the skills directories updated
    :param synced_command_files: paths of all the skills markdowns updated
    """

    plugins_root: Path
    claude_dir: Path
    synced_skill_dirs: list[Path] = field(default_factory=lambda: [])
    synced_command_files: list[Path] = field(default_factory=lambda: [])

    @property
    def skill_names(self) -> list[str]:
        """
        Returns the names of all skills that have been synced

        :returns list of skill directory names under .claude/skills/
        """
        return [d.name for d in self.synced_skill_dirs]

    def _find_plugin_roots(self) -> list[Path]:
        """
        Recursively searches plugins_root for directories that contain a
        .claude-plugin/plugin.json manifest file

        :returns sorted list of plugin root paths
        """
        if not self.plugins_root.exists():
            return []
        roots = {
            _plugin.parent.parent
            for _plugin in self.plugins_root.rglob(".claude-plugin/plugin.json")
        }
        return sorted(roots)

    def _sync_skills(self, plugin_root: Path) -> None:
        """
        Copies each skill folder from the plugin into .claude/skills/

        :param plugin_root: root directory of the plugin
        """
        skills_dir = plugin_root / "skills"
        if not skills_dir.exists():
            return
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            skill_name = skill_md.parent.name
            target = self.claude_dir / "skills" / skill_name
            target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill_md.parent, target, dirs_exist_ok=True)
            self.synced_skill_dirs.append(target)

    def _sync_commands(self, plugin_root: Path) -> None:
        """
        Copies each command file from the plugin into .claude/commands/

        :param plugin_root: root directory of the plugin
        """
        cmd_dir = plugin_root / "commands"
        if not cmd_dir.exists():
            return
        target_dir = self.claude_dir / "commands"
        target_dir.mkdir(parents=True, exist_ok=True)
        for cmd_file in sorted(cmd_dir.glob("*.md")):
            target = target_dir / cmd_file.name
            shutil.copy2(cmd_file, target)
            self.synced_command_files.append(target)

    def sync(self):
        """
        Copies all skills and commands from every plugin into the .claude/ directory
        """
        for plugin_root in self._find_plugin_roots():
            self._sync_skills(plugin_root=plugin_root)
            self._sync_commands(plugin_root=plugin_root)

    def clean(self):
        """
        Removes all skill directories and command files that were synced
        """
        for skill_dir in self.synced_skill_dirs:
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
        for cmd_file in self.synced_command_files:
            if cmd_file.exists():
                cmd_file.unlink()
        self.synced_skill_dirs.clear()
        self.synced_command_files.clear()
