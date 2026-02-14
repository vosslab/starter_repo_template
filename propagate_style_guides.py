#!/usr/bin/env python3

import os
import sys
import stat
import shutil
import argparse
import filecmp

# ANSI color codes
class Colors:
	RESET = '\033[0m'
	RED = '\033[91m'
	GREEN = '\033[92m'
	YELLOW = '\033[93m'
	BLUE = '\033[94m'
	MAGENTA = '\033[95m'
	CYAN = '\033[96m'

# Editable file lists
STYLE_FILES = [
	'PYTHON_STYLE.md',
	'MARKDOWN_STYLE.md',
	'REPO_STYLE.md',
	'AUTHORS.md',
]
DEVEL_SCRIPTS = [
	'commit_changelog.py',
	'submit_to_pypi.py',
]
TEST_SCRIPTS = [
	'check_ascii_compliance.py',
	'fix_ascii_compliance.py',
	'fix_whitespace.py',
	'git_file_utils.py',
	'pyrightconfig.json',
	'test_import_requirements.py',
	'test_import_star.py',
]
DEPRECATED_TEST_SCRIPTS = [
	'run_ascii_compliance.sh',
	'run_pyflakes.sh',
	'run_ascii_compliance.py',
	'test_repo_hygiene.py',
	'test_pyflakes.py',
]
DEPRECATED_GITIGNORE_ENTRIES = [
	'shebang_report.txt',
	'pyflakes.txt',
	'bandit.txt',
	'pyright.txt',
	'ascii_compliance.txt',
]
REQUIRED_GITIGNORE_ENTRIES = [
	'report_shebang.txt',
	'report_pyflakes.txt',
	'report_ascii_compliance.txt',
	'.DS_Store',
	'report_bandit.txt',
	'report_pyright.txt',
]
SKIP_WALK_DIRS = {
	'.git',
	'.mypy_cache',
	'.pytest_cache',
	'old_shell_folder',
	'.venv',
	'.system',
	'__pycache__',
	'build',
	'dist',
	'node_modules',
	'venv',
}
COUNTER_EXPECTED = {
	'copied': 0,
	'updated': 0,
	'updated_agents': 0,
	'created_agents': 0,
	'created_changelog': 0,
	'skipped_same': 0,
	'skipped_source': 0,
	'skipped_non_repo': 0,
	'errors': 0,
	'copied_tests': 0,
	'updated_tests': 0,
	'skipped_same_tests': 0,
	'skipped_source_tests': 0,
	'skipped_tests_no_python': 0,
	'removed_deprecated_tests': 0,
	'created_conftest': 0,
	'git_perms_changed': 0,
	'git_perms_unchanged': 0,
	'created_tests_dirs': 0,
	'created_devel_dirs': 0,
	'skipped_source_devel': 0,
	'gitignore_created': 0,
	'gitignore_updated': 0,
	'gitignore_lines_added': 0,
	'gitignore_cleaned': 0,
	'gitignore_duplicates_removed': 0,
	'gitignore_whitespace_cleaned': 0,
	'gitignore_deprecated_removed': 0,
	'gitignore_deprecated_entries_removed': 0,
	'skipped_same_devel': 0,
	'copied_devel': 0,
	'updated_devel': 0,
	'skipped_devel_no_pyproject': 0,
}


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(
		description=(
			"Copy style guides and repo docs into each repo under ~/nsh/, "
			"placing them in docs/."
		)
	)
	parser.add_argument(
		'-n', '--dry-run', dest='dry_run',
		help='Only display planned changes', action='store_true'
	)
	parser.add_argument(
		'--source-dir', dest='source_dir',
		default=None,
		help=(
			'Directory containing style guides (default: <base>/junk-drawer when present; '
			'otherwise the repo root containing this script; docs/ is preferred when present)'
		)
	)
	parser.add_argument(
		'--repo', dest='repo_name',
		default=None,
		help='Only update the named repo under ~/nsh (directory name)'
	)
	parser.set_defaults(dry_run=False)
	args = parser.parse_args()
	return args


#============================================
def choose_style_destination(repo_dir: str, styles: list[str]) -> str:
	"""
	Choose a destination directory for style guides in a repo.

	Args:
		repo_dir (str): Repository directory.
		styles (list[str]): Style guide filenames.

	Returns:
		str: Destination directory for style guides.
	"""
	_ = styles
	return os.path.join(repo_dir, 'docs')


#============================================
def is_repo_dir(repo_dir: str) -> bool:
	"""
	Check whether a directory looks like a git repository.

	Args:
		repo_dir (str): Candidate repository directory.

	Returns:
		bool: True if a .git entry exists, False otherwise.
	"""
	return os.path.exists(os.path.join(repo_dir, '.git'))


#============================================
def find_repo_root(start_dir: str) -> str | None:
	"""
	Find the nearest ancestor that contains the expected style guides.

	Args:
		start_dir (str): Starting directory.

	Returns:
		str | None: Repo root path when found, otherwise None.
	"""
	required_paths = (
		os.path.join('docs', 'PYTHON_STYLE.md'),
		os.path.join('docs', 'MARKDOWN_STYLE.md'),
		os.path.join('docs', 'REPO_STYLE.md'),
	)
	current = os.path.abspath(start_dir)
	while True:
		if all(
			os.path.isfile(os.path.join(current, rel_path))
			for rel_path in required_paths
		):
			return current
		parent = os.path.dirname(current)
		if parent == current:
			return None
		current = parent


#============================================
def ensure_git_perms(repo_dir: str, dry_run: bool) -> bool:
	"""
	Make .git group-writable so Git can create .git/index.lock and update the index.

	Note: This only helps if the user is in the repo group.
	"""
	git_dir = os.path.join(repo_dir, '.git')
	if not os.path.isdir(git_dir):
		return False

	changed = False

	def add_group_write(path: str) -> None:
		nonlocal changed
		try:
			st = os.stat(path, follow_symlinks=False)
		except OSError:
			return
		mode = stat.S_IMODE(st.st_mode)
		new_mode = mode | 0o020  # g+w
		if new_mode == mode:
			return
		changed = True
		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} chmod g+w {path}")
			return
		os.chmod(path, new_mode, follow_symlinks=False)

	add_group_write(git_dir)

	index_path = os.path.join(git_dir, 'index')
	if os.path.exists(index_path):
		add_group_write(index_path)

	for root, dirs, files in os.walk(git_dir, topdown=True, followlinks=False):
		for d in dirs:
			add_group_write(os.path.join(root, d))
		for f in files:
			add_group_write(os.path.join(root, f))

	return changed


#============================================
def ensure_agents_coding_style(
	agents_path: str,
	style_paths: dict[str, str],
	dry_run: bool
) -> bool:
	"""
	Ensure AGENTS.md contains required repo guidance sections and lines.

	Args:
		agents_path (str): Path to AGENTS.md.
		style_paths (dict[str, str]): Map of style filenames to repo-relative paths.
		dry_run (bool): If True, do not write changes.

	Returns:
		bool: True if file was modified, False otherwise.
	"""
	with open(agents_path, 'r', encoding='utf-8') as f:
		content = f.read()

	lines = content.splitlines(keepends=True)

	python_path = style_paths['PYTHON_STYLE.md']
	markdown_path = style_paths['MARKDOWN_STYLE.md']
	repo_style_path = style_paths['REPO_STYLE.md']

	python_line = f"See Python coding style in {python_path}.\n"
	markdown_line = f"See Markdown style in {markdown_path}.\n"
	repo_style_line = f"See repo style in {repo_style_path}.\n"
	changelog_line = "When making edits, document them in docs/CHANGELOG.md.\n"
	user_request_line = (
		"When in doubt, implement the changes the user asked for rather than waiting "
		"for a response; the user is not the best reader and will likely miss your "
		"request and then be confused why it was not implemented or fixed.\n"
	)
	tests_required_line = (
		"When changing code always run tests, documentation does not require tests.\n"
	)
	tests_allowed_line = (
		"Agents may run programs in the tests folder, including smoke tests and "
		"pyflakes/mypy runner scripts.\n"
	)
	environment_header = "## Environment\n"
	macos_python312_interpreter_line = (
		"Codex must run Python using `/opt/homebrew/opt/python@3.12/bin/python3.12` "
		"(use Python 3.12 only).\nThis is only for Codex's runtime, not a requirement "
		"for repo scripts.\n"
	)
	macos_site_packages_line = (
		"On this user's macOS (Homebrew Python 3.12), Python modules are installed to "
		"`/opt/homebrew/lib/python3.12/site-packages/`.\n"
	)
	is_macos = (sys.platform == 'darwin')

	def insert_after_environment_header(insert_lines: list[str]) -> bool:
		for i, line in enumerate(lines):
			if line.strip() == '## Environment':
				lines[i + 1:i + 1] = insert_lines
				return True
		return False

	changed = False
	for filename, desired_path in (
		('PYTHON_STYLE.md', python_path),
		('MARKDOWN_STYLE.md', markdown_path),
		('REPO_STYLE.md', repo_style_path),
	):
		if desired_path == filename:
			continue
		for i, line in enumerate(lines):
			if filename in line and desired_path not in line:
				lines[i] = line.replace(filename, desired_path)
				changed = True

	for i, line in enumerate(lines):
		if 'CHANGELOG.md' in line and 'docs/CHANGELOG.md' not in line:
			lines[i] = line.replace('CHANGELOG.md', 'docs/CHANGELOG.md')
			changed = True

	updated_content = ''.join(lines)

	has_header = '## Coding Style' in updated_content
	has_python = 'PYTHON_STYLE.md' in updated_content
	has_markdown = 'MARKDOWN_STYLE.md' in updated_content
	has_repo_style = 'REPO_STYLE.md' in updated_content
	has_changelog = 'docs/CHANGELOG.md' in updated_content
	has_user_request_line = (
		"When in doubt, implement the changes the user asked for" in updated_content
	)
	has_tests_required_line = (
		"When changing code always run tests" in updated_content
	)
	has_tests_allowed = 'Agents may run programs in the tests folder' in updated_content
	has_environment_header = '## Environment' in updated_content
	has_macos_python312_interpreter = (
		'/opt/homebrew/opt/python@3.12/bin/python3.12' in updated_content
	)
	has_macos_site_packages = '/opt/homebrew/lib/python3.12/site-packages/' in updated_content

	lines_to_add = []
	if not has_header:
		lines_to_add.append('## Coding Style\n')
	if not has_python:
		lines_to_add.append(python_line)
	if not has_markdown:
		lines_to_add.append(markdown_line)
	if not has_repo_style:
		lines_to_add.append(repo_style_line)
	if not has_changelog:
		lines_to_add.append(changelog_line)
	if not has_user_request_line:
		lines_to_add.append(user_request_line)
	if not has_tests_required_line:
		lines_to_add.append(tests_required_line)
	if not has_tests_allowed:
		lines_to_add.append(tests_allowed_line)

	environment_lines: list[str] = []
	if is_macos and not has_macos_python312_interpreter:
		environment_lines.append(macos_python312_interpreter_line)
	if is_macos and not has_macos_site_packages:
		environment_lines.append(macos_site_packages_line)

	if environment_lines:
		if has_environment_header:
			if insert_after_environment_header(environment_lines):
				changed = True
		else:
			lines_to_add.append('\n')
			lines_to_add.append(environment_header)
			lines_to_add.extend(environment_lines)

	if not lines_to_add and not changed:
		return False

	updated_content = ''.join(lines)
	needs_newline = (len(updated_content) > 0 and not updated_content.endswith('\n'))
	if dry_run:
		return True

	if lines_to_add:
		if needs_newline:
			updated_content += '\n'
		updated_content += ''.join(lines_to_add)

	with open(agents_path, 'w', encoding='utf-8') as f:
		f.write(updated_content)

	return True


#============================================
def build_agents_coding_style_block(style_paths: dict[str, str]) -> str:
	"""
	Build a minimal AGENTS.md block for new repos.

	Args:
		style_paths (dict[str, str]): Map of style filenames to repo-relative paths.

	Returns:
		str: Content for AGENTS.md with coding style and environment notes.
	"""
	python_path = style_paths['PYTHON_STYLE.md']
	markdown_path = style_paths['MARKDOWN_STYLE.md']
	repo_style_path = style_paths['REPO_STYLE.md']

	lines = [
		'## Coding Style\n',
		f"See Python coding style in {python_path}.\n",
		f"See Markdown style in {markdown_path}.\n",
		f"See repo style in {repo_style_path}.\n",
		'When making edits, document them in docs/CHANGELOG.md.\n',
		(
			"When in doubt, implement the changes the user asked for rather than waiting "
			"for a response; the user is not the best reader and will likely miss your "
			"request and then be confused why it was not implemented or fixed.\n"
		),
		"When changing code always run tests, documentation does not require tests.\n",
		(
			"Agents may run programs in the tests folder, including smoke tests "
			"and pyflakes/mypy runner scripts.\n"
		),
	]

	if sys.platform == 'darwin':
		lines.extend(
			[
				'\n',
				'## Environment\n',
				(
					"Codex must run Python using `/opt/homebrew/opt/python@3.12/bin/python3.12` "
					"(use Python 3.12 only). This is only for Codex's runtime, not a "
					"requirement for repo scripts.\n"
				),
				(
					"On this user's macOS (Homebrew Python 3.12), Python modules are installed to "
					"`/opt/homebrew/lib/python3.12/site-packages/`.\n"
				),
			]
		)
	return ''.join(lines)


#============================================
def ensure_agents_file(
	agents_path: str,
	style_paths: dict[str, str],
	dry_run: bool
) -> bool:
	"""
	Create AGENTS.md if missing; otherwise ensure it has coding style lines.

	Args:
		agents_path (str): Path to AGENTS.md.
		style_paths (dict[str, str]): Map of style filenames to repo-relative paths.
		dry_run (bool): If True, do not write changes.

	Returns:
		bool: True if file was created or modified, False otherwise.
	"""
	if not os.path.exists(agents_path):
		if dry_run:
			return True
		content = build_agents_coding_style_block(style_paths)
		with open(agents_path, 'w', encoding='utf-8') as f:
			f.write(content)
		return True

	return ensure_agents_coding_style(agents_path, style_paths, dry_run)


#============================================
def ensure_changelog_file(changelog_path: str, dry_run: bool) -> bool:
	"""
	Create docs/CHANGELOG.md if missing.

	Args:
		changelog_path (str): Path to docs/CHANGELOG.md.
		dry_run (bool): If True, do not write changes.

	Returns:
		bool: True if file was created, False otherwise.
	"""
	if os.path.exists(changelog_path):
		return False

	if dry_run:
		return True

	with open(changelog_path, 'w', encoding='utf-8') as f:
		f.write('')
	return True


#============================================
def ensure_tests_dir(tests_dir: str, dry_run: bool) -> bool:
	"""
	Create the tests directory if missing.

	Args:
		tests_dir (str): Path to tests directory.
		dry_run (bool): If True, do not write changes.

	Returns:
		bool: True if directory was created, False otherwise.
	"""
	if os.path.isdir(tests_dir):
		return False
	if dry_run:
		return True
	os.makedirs(tests_dir, exist_ok=True)
	return True


#============================================
def remove_gitignore_entries(gitignore_path: str, entries: list[str], dry_run: bool) -> int:
	"""
	Remove deprecated entries from .gitignore file.

	Args:
		gitignore_path (str): Path to .gitignore file.
		entries (list[str]): List of gitignore patterns to remove.
		dry_run (bool): If True, do not write changes.

	Returns:
		int: Number of lines removed.
	"""
	if not os.path.isfile(gitignore_path):
		return 0

	with open(gitignore_path, 'r', encoding='utf-8') as f:
		lines = [line.rstrip('\n') for line in f]

	# Remove entries that match deprecated patterns
	entries_set = set(entry.strip() for entry in entries)
	filtered_lines = []
	removed_count = 0

	for line in lines:
		stripped = line.strip()
		if stripped in entries_set:
			removed_count += 1
			continue
		filtered_lines.append(line.rstrip())

	if removed_count == 0:
		return 0

	if dry_run:
		return removed_count

	# Write back without deprecated entries
	with open(gitignore_path, 'w', encoding='utf-8') as f:
		for line in filtered_lines:
			f.write(line + '\n')

	return removed_count


#============================================
def deduplicate_gitignore(gitignore_path: str, dry_run: bool) -> tuple[int, bool]:
	"""
	Remove duplicate lines and trailing whitespace from .gitignore file.
	Preserves all empty lines and comments for visual grouping.

	Args:
		gitignore_path (str): Path to .gitignore file.
		dry_run (bool): If True, do not write changes.

	Returns:
		tuple[int, bool]: (duplicates_removed, whitespace_cleaned)
	"""
	if not os.path.isfile(gitignore_path):
		return (0, False)

	with open(gitignore_path, 'r', encoding='utf-8') as f:
		original_lines = [line.rstrip('\n') for line in f]

	# Strip trailing whitespace from all lines
	stripped_lines = [line.rstrip() for line in original_lines]

	# Remove duplicates while preserving order, but keep all empty lines
	seen = set()
	unique_lines = []
	for line in stripped_lines:
		# Always keep empty lines (for visual grouping/comments)
		if line == '':
			unique_lines.append(line)
		elif line not in seen:
			seen.add(line)
			unique_lines.append(line)

	duplicates_removed = len(stripped_lines) - len(unique_lines)
	whitespace_cleaned = any(orig != stripped for orig, stripped in zip(original_lines, stripped_lines))

	# Check if any changes needed
	if duplicates_removed == 0 and not whitespace_cleaned:
		return (0, False)

	if dry_run:
		return (duplicates_removed, whitespace_cleaned)

	# Write back cleaned content
	with open(gitignore_path, 'w', encoding='utf-8') as f:
		for line in unique_lines:
			f.write(line + '\n')

	return (duplicates_removed, whitespace_cleaned)


#============================================
def ensure_gitignore_entries(gitignore_path: str, entries: list[str], dry_run: bool) -> tuple[bool, int]:
	"""
	Ensure .gitignore contains required entries.

	Args:
		gitignore_path (str): Path to .gitignore file.
		entries (list[str]): List of gitignore patterns to ensure.
		dry_run (bool): If True, do not write changes.

	Returns:
		tuple[bool, int]: (file_created, lines_added)
	"""
	existing_lines = []
	file_exists = os.path.isfile(gitignore_path)

	if file_exists:
		with open(gitignore_path, 'r', encoding='utf-8') as f:
			# Strip all whitespace from both ends for comparison
			existing_lines = [line.strip() for line in f]

	# Check which entries are missing
	missing_entries = []
	for entry in entries:
		if entry not in existing_lines:
			missing_entries.append(entry)

	if not missing_entries:
		return (False, 0)

	if dry_run:
		return (not file_exists, len(missing_entries))

	# Add missing entries
	with open(gitignore_path, 'a', encoding='utf-8') as f:
		# Ensure file ends with newline before appending
		if file_exists and existing_lines:
			# Check if file actually ends with newline by reading it
			with open(gitignore_path, 'rb') as check_f:
				check_f.seek(-1, 2)
				last_byte = check_f.read(1)
				if last_byte != b'\n':
					f.write('\n')
		for entry in missing_entries:
			f.write(entry + '\n')

	return (not file_exists, len(missing_entries))


#============================================
def repo_has_pyproject_toml(repo_dir: str) -> bool:
	"""
	Check whether a repo contains a pyproject.toml file anywhere under it.

	Args:
		repo_dir (str): Repository directory.

	Returns:
		bool: True if any pyproject.toml exists, False otherwise.
	"""
	for root, dirs, files in os.walk(repo_dir, topdown=True, followlinks=False):
		dirs[:] = [
			d for d in dirs
			if d not in SKIP_WALK_DIRS and not d.startswith('.')
		]
		if 'pyproject.toml' in files:
			return True
	return False


#============================================
def repo_has_python_files(repo_dir: str) -> bool:
	"""
	Check whether a repo contains any Python files.

	Args:
		repo_dir (str): Repository directory.

	Returns:
		bool: True if any .py file exists, False otherwise.
	"""
	for root, dirs, files in os.walk(repo_dir, topdown=True, followlinks=False):
		dirs[:] = [
			d for d in dirs
			if d not in SKIP_WALK_DIRS and not d.startswith('.')
		]
		for name in files:
			if name.endswith('.py'):
				return True
	return False


#============================================
def resolve_target_repo(base_dir: str, repo_name: str | None) -> str | None:
	"""
	Resolve and validate an optional single target repo under base_dir.

	Args:
		base_dir (str): Base directory that contains repos.
		repo_name (str | None): Optional repo directory name.

	Returns:
		str | None: Absolute repo path if provided, otherwise None.
	"""
	if not repo_name:
		return None
	target_repo = os.path.join(base_dir, repo_name)
	if not os.path.isdir(target_repo):
		raise FileNotFoundError(
			f"Repo not found under {base_dir}: {repo_name}"
		)
	if not is_repo_dir(target_repo):
		raise FileNotFoundError(
			f"Repo missing .git under {base_dir}: {repo_name}"
		)
	return target_repo


#============================================
def resolve_source_dir(base_dir: str, source_dir_arg: str | None) -> str:
	"""
	Resolve the source directory used for propagation.

	Args:
		base_dir (str): Base directory for default lookup.
		source_dir_arg (str | None): Optional user-provided source dir.

	Returns:
		str: Absolute source directory path.
	"""
	source_dir = source_dir_arg
	if source_dir is None:
		preferred_source = os.path.join(base_dir, 'junk-drawer')
		if os.path.isdir(preferred_source):
			source_dir = preferred_source
		else:
			script_dir = os.path.dirname(os.path.abspath(__file__))
			detected_repo_root = find_repo_root(script_dir)
			if detected_repo_root is None:
				raise FileNotFoundError(
					"Default source dir not found. Provide --source-dir."
				)
			source_dir = detected_repo_root
	return os.path.abspath(os.path.expanduser(source_dir))


#============================================
def build_source_maps(
	source_dir: str,
	styles: list[str],
	devel_scripts: list[str],
	test_scripts: list[str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], list[str]]:
	"""
	Build source-file maps for style guides, devel scripts, and test scripts.

	Returns:
		tuple: (style_map, devel_map, test_map, final_test_scripts)
	"""
	source_candidates = [
		os.path.join(source_dir, 'docs'),
		source_dir,
	]

	source_map: dict[str, str] = {}
	for filename in styles:
		source_file = None
		for candidate in source_candidates:
			candidate_file = os.path.join(candidate, filename)
			if os.path.isfile(candidate_file):
				source_file = candidate_file
				break
		if source_file is None:
			raise FileNotFoundError(
				f"Source file not found in {source_candidates}: {filename}"
			)
		source_map[filename] = source_file

	source_devel_dir = os.path.join(source_dir, 'devel')
	devel_source_map: dict[str, str] = {}
	for filename in devel_scripts:
		source_file = os.path.join(source_devel_dir, filename)
		if not os.path.isfile(source_file):
			raise FileNotFoundError(
				f"Source file not found: {source_file}"
			)
		devel_source_map[filename] = source_file

	source_tests_dir = os.path.join(source_dir, 'tests')
	if not os.path.isdir(source_tests_dir):
		raise FileNotFoundError(
			f"Source tests dir not found: {source_tests_dir}"
		)

	final_test_scripts = list(test_scripts)
	for entry in sorted(os.listdir(source_tests_dir)):
		if not entry.startswith('test_'):
			continue
		if not entry.endswith('.py'):
			continue
		if entry in final_test_scripts:
			continue
		final_test_scripts.append(entry)

	test_source_map: dict[str, str] = {}
	for filename in final_test_scripts:
		source_file = os.path.join(source_tests_dir, filename)
		if not os.path.isfile(source_file):
			raise FileNotFoundError(
				f"Source file not found: {source_file}"
			)
		test_source_map[filename] = source_file

	return (source_map, devel_source_map, test_source_map, final_test_scripts)


#============================================
def collect_repo_dirs(base_dir: str, target_repo: str | None) -> list[str]:
	"""
	Collect repository directories to process.
	"""
	if target_repo:
		return [target_repo]
	repo_dirs: list[str] = []
	for entry in os.scandir(base_dir):
		if not entry.is_dir(follow_symlinks=False):
			continue
		if entry.name.startswith('.'):
			continue
		repo_dirs.append(entry.path)
	return repo_dirs


#============================================
def process_gitignore(repo_dir: str, dry_run: bool) -> tuple[int, int, int, int, int, int, int, int]:
	"""
	Clean and update .gitignore for one repo.

	Returns:
		tuple:
			(created, updated, lines_added, cleaned, dup_removed, whitespace_cleaned,
			 deprecated_removed_files, deprecated_removed_entries)
	"""
	gitignore_path = os.path.join(repo_dir, '.gitignore')
	created_count = 0
	updated_count = 0
	lines_added_total = 0
	cleaned_count = 0
	dup_removed = 0
	whitespace_cleaned = 0
	deprecated_removed_files = 0
	deprecated_removed_entries = 0

	deprecated_removed = remove_gitignore_entries(
		gitignore_path,
		DEPRECATED_GITIGNORE_ENTRIES,
		dry_run,
	)
	if deprecated_removed > 0:
		deprecated_removed_files = 1
		deprecated_removed_entries = deprecated_removed
		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} remove {deprecated_removed} deprecated entries from {gitignore_path}")
		else:
			print(f"{Colors.BLUE}[CLEANED]{Colors.RESET} removed {deprecated_removed} deprecated entries from {gitignore_path}")

	duplicates, whitespace = deduplicate_gitignore(gitignore_path, dry_run)
	if duplicates > 0 or whitespace:
		cleaned_count = 1
		dup_removed = duplicates
		if whitespace:
			whitespace_cleaned = 1

		message_parts = []
		if duplicates > 0:
			message_parts.append(f"{duplicates} duplicate lines")
		if whitespace:
			message_parts.append("trailing whitespace")
		message = " and ".join(message_parts)

		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} remove {message} from {gitignore_path}")
		else:
			print(f"{Colors.BLUE}[CLEANED]{Colors.RESET} removed {message} from {gitignore_path}")

	created, lines_added = ensure_gitignore_entries(
		gitignore_path,
		REQUIRED_GITIGNORE_ENTRIES,
		dry_run,
	)
	if created:
		created_count = 1
		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} create {gitignore_path} with {lines_added} entries")
		else:
			print(f"{Colors.BLUE}[CREATED]{Colors.RESET} {gitignore_path} with {lines_added} entries")
	elif lines_added > 0:
		updated_count = 1
		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} add {lines_added} entries to {gitignore_path}")
		else:
			print(f"{Colors.BLUE}[UPDATED]{Colors.RESET} added {lines_added} entries to {gitignore_path}")
	lines_added_total += lines_added

	return (
		created_count,
		updated_count,
		lines_added_total,
		cleaned_count,
		dup_removed,
		whitespace_cleaned,
		deprecated_removed_files,
		deprecated_removed_entries,
	)


#============================================
def remove_deprecated_tests(tests_dir: str, dry_run: bool) -> int:
	"""
	Remove deprecated tests scripts from one repo's tests directory.
	"""
	removed = 0
	for deprecated_test_file in DEPRECATED_TEST_SCRIPTS:
		deprecated_test_path = os.path.join(tests_dir, deprecated_test_file)
		if not os.path.isfile(deprecated_test_path):
			continue
		if dry_run:
			print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} remove {deprecated_test_path}")
		else:
			os.remove(deprecated_test_path)
			print(f"{Colors.BLUE}[REMOVED]{Colors.RESET} {deprecated_test_path}")
		removed += 1
	return removed


#============================================
def format_count(
	value: int,
	always_color: str | None = None,
	positive_color: str | None = None,
) -> str:
	"""
	Format an integer with optional color rules.
	"""
	if always_color is not None:
		return f"{always_color}{value}{Colors.RESET}"
	if positive_color is not None and value > 0:
		return f"{positive_color}{value}{Colors.RESET}"
	return str(value)


#============================================
def print_metric_list(metrics: list[dict[str, object]]) -> None:
	"""
	Print a list of summary metrics.
	"""
	for metric in metrics:
		label = str(metric['label'])
		value = int(metric['value'])
		expected = metric.get('expected')
		always_color = metric.get('always_color')
		positive_color = metric.get('positive_color')
		formatted = format_count(
			value,
			always_color=str(always_color) if always_color else None,
			positive_color=str(positive_color) if positive_color else None,
		)
		if expected is not None:
			formatted = f"{formatted} (expected {int(expected)})"
		print(f"{label}: {formatted}")


#============================================
def print_by_file_blocks(blocks: list[dict[str, object]]) -> None:
	"""
	Print grouped per-file counters.
	"""
	for block in blocks:
		title = str(block['title'])
		filenames = list(block['filenames'])
		counts = dict(block['counts'])
		always_color = block.get('always_color')
		positive_color = block.get('positive_color')
		print(title)
		for filename in filenames:
			value = int(counts[filename])
			formatted = format_count(
				value,
				always_color=str(always_color) if always_color else None,
				positive_color=str(positive_color) if positive_color else None,
			)
			print(f"  {filename}: {formatted}")


#============================================
def print_summary_report(summary: dict[str, object]) -> None:
	"""
	Print propagation summary from a nested summary dictionary.
	"""
	context = dict(summary['context'])
	skipped = dict(summary['skipped'])
	changes = dict(summary['changes'])
	errors = int(summary['errors'])

	print("")
	print(f"{Colors.CYAN}Base dir:{Colors.RESET} {context['base_dir']}")
	print(f"{Colors.CYAN}Source dir:{Colors.RESET} {context['source_dir']}")
	print("")
	print(f"{Colors.CYAN}Skipped summary:{Colors.RESET}")
	print_metric_list(list(skipped['metrics']))
	print_by_file_blocks(list(skipped['by_file']))
	print("")
	if errors > 0:
		print(f"Errors:   {Colors.RED}{errors}{Colors.RESET}")
	else:
		print(f"Errors:   {Colors.GREEN}{errors}{Colors.RESET}")
	print("")
	print(f"{Colors.CYAN}Changes summary:{Colors.RESET}")
	print_metric_list(list(changes['metrics']))
	print_by_file_blocks(list(changes['by_file']))


#============================================
def main():
	"""
	Copy style guides to each repo under base_dir and update AGENTS.md if needed.
	"""
	args = parse_args()

	base_dir = os.path.abspath(os.path.expanduser('~/nsh'))
	target_repo = resolve_target_repo(base_dir, args.repo_name)
	source_dir = resolve_source_dir(base_dir, args.source_dir)
	styles = list(STYLE_FILES)
	devel_scripts = list(DEVEL_SCRIPTS)
	test_scripts = list(TEST_SCRIPTS)
	source_map, devel_source_map, test_source_map, test_scripts = build_source_maps(
		source_dir,
		styles,
		devel_scripts,
		test_scripts,
	)

	counts = {key: 0 for key in COUNTER_EXPECTED}
	skipped_same_by_file = {filename: 0 for filename in styles}
	copied_by_file = {filename: 0 for filename in styles}
	updated_by_file = {filename: 0 for filename in styles}
	skipped_same_tests_by_file = {filename: 0 for filename in test_scripts}
	copied_tests_by_file = {filename: 0 for filename in test_scripts}
	updated_tests_by_file = {filename: 0 for filename in test_scripts}
	skipped_tests_no_python_by_file = {filename: 0 for filename in test_scripts}
	skipped_same_devel_by_file = {filename: 0 for filename in devel_scripts}
	copied_devel_by_file = {filename: 0 for filename in devel_scripts}
	updated_devel_by_file = {filename: 0 for filename in devel_scripts}
	skipped_devel_no_pyproject_by_file = {filename: 0 for filename in devel_scripts}

	repo_dirs = collect_repo_dirs(base_dir, target_repo)

	for repo_dir in repo_dirs:
		if not is_repo_dir(repo_dir):
			counts['skipped_non_repo'] += 1
			continue

		if ensure_git_perms(repo_dir, args.dry_run):
			counts['git_perms_changed'] += 1
		else:
			counts['git_perms_unchanged'] += 1

		(
			gitignore_created_inc,
			gitignore_updated_inc,
			gitignore_lines_added_inc,
			gitignore_cleaned_inc,
			gitignore_duplicates_removed_inc,
			gitignore_whitespace_cleaned_inc,
			gitignore_deprecated_removed_inc,
			gitignore_deprecated_entries_removed_inc,
		) = process_gitignore(repo_dir, args.dry_run)
		counts['gitignore_created'] += gitignore_created_inc
		counts['gitignore_updated'] += gitignore_updated_inc
		counts['gitignore_lines_added'] += gitignore_lines_added_inc
		counts['gitignore_cleaned'] += gitignore_cleaned_inc
		counts['gitignore_duplicates_removed'] += gitignore_duplicates_removed_inc
		counts['gitignore_whitespace_cleaned'] += gitignore_whitespace_cleaned_inc
		counts['gitignore_deprecated_removed'] += gitignore_deprecated_removed_inc
		counts['gitignore_deprecated_entries_removed'] += gitignore_deprecated_entries_removed_inc

		dest_dir = choose_style_destination(repo_dir, styles)
		docs_dir = os.path.join(repo_dir, 'docs')
		if not os.path.isdir(docs_dir):
			if args.dry_run:
				print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} mkdir {docs_dir}")
			else:
				os.makedirs(docs_dir, exist_ok=True)

		tests_dir = os.path.join(repo_dir, 'tests')
		if ensure_tests_dir(tests_dir, args.dry_run):
			if args.dry_run:
				print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} mkdir {tests_dir}")
			counts['created_tests_dirs'] += 1
		conftest_path = os.path.join(tests_dir, 'conftest.py')
		if not os.path.isfile(conftest_path):
			if args.dry_run:
				print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} create {conftest_path}")
			else:
				with open(conftest_path, 'w', encoding='utf-8'):
					pass
				print(f"{Colors.BLUE}[CREATED]{Colors.RESET} {conftest_path}")
			counts['created_conftest'] += 1

		counts['removed_deprecated_tests'] += remove_deprecated_tests(tests_dir, args.dry_run)

		devel_dir = os.path.join(repo_dir, 'devel')
		if not os.path.isdir(devel_dir):
			if args.dry_run:
				print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} mkdir {devel_dir}")
			else:
				os.makedirs(devel_dir, exist_ok=True)
			counts['created_devel_dirs'] += 1

		changelog_path = os.path.join(docs_dir, 'CHANGELOG.md')
		if ensure_changelog_file(changelog_path, args.dry_run):
			if args.dry_run:
				print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} create {changelog_path}")
			counts['created_changelog'] += 1

		for filename in styles:
			source_file = source_map[filename]
			dest_file = os.path.join(dest_dir, filename)

			if os.path.abspath(dest_file) == source_file:
				counts['skipped_source'] += 1
				print(f"{Colors.CYAN}[SKIP SOURCE]{Colors.RESET} {dest_file}")
				continue

			try:
				dest_exists = os.path.isfile(dest_file)
				is_same = False
				if dest_exists:
					is_same = filecmp.cmp(source_file, dest_file, shallow=False)
				if is_same:
					counts['skipped_same'] += 1
					skipped_same_by_file[filename] += 1
					continue

				if args.dry_run:
					action = 'update' if dest_exists else 'copy'
					print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} {action} {source_file} -> {dest_file}")
				else:
					shutil.copy2(source_file, dest_file)
				if dest_exists:
					counts['updated'] += 1
					updated_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[UPDATED]{Colors.RESET} {source_file} -> {dest_file}")
				else:
					counts['copied'] += 1
					copied_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[COPIED]{Colors.RESET} {source_file} -> {dest_file}")
			except Exception as e:
				counts['errors'] += 1
				print(f"{Colors.RED}[ERROR]{Colors.RESET} {repo_dir}: {e}")

		repo_python = repo_has_python_files(repo_dir)
		for filename in test_scripts:
			if filename.startswith('test_') and filename.endswith('.py') and not repo_python:
				counts['skipped_tests_no_python'] += 1
				skipped_tests_no_python_by_file[filename] += 1
				if args.dry_run:
					print(
						f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} "
						f"skip {filename} (no Python files) in {repo_dir}"
					)
				continue
			source_file = test_source_map[filename]
			dest_file = os.path.join(tests_dir, filename)

			if os.path.abspath(dest_file) == source_file:
				counts['skipped_source_tests'] += 1
				if not args.dry_run:
					print(f"{Colors.CYAN}[SKIP SOURCE]{Colors.RESET} {dest_file}")
				continue

			try:
				dest_exists = os.path.isfile(dest_file)
				is_same = False
				if dest_exists:
					is_same = filecmp.cmp(source_file, dest_file, shallow=False)
				if is_same:
					counts['skipped_same_tests'] += 1
					skipped_same_tests_by_file[filename] += 1
					continue

				if args.dry_run:
					action = 'update' if dest_exists else 'copy'
					print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} {action} {source_file} -> {dest_file}")
				else:
					shutil.copy2(source_file, dest_file)
				if dest_exists:
					counts['updated_tests'] += 1
					updated_tests_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[UPDATED]{Colors.RESET} {source_file} -> {dest_file}")
				else:
					counts['copied_tests'] += 1
					copied_tests_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[COPIED]{Colors.RESET} {source_file} -> {dest_file}")
			except Exception as e:
				counts['errors'] += 1
				print(f"{Colors.RED}[ERROR]{Colors.RESET} {repo_dir}: {e}")

		for filename in devel_scripts:
			if filename == 'submit_to_pypi.py' and not repo_has_pyproject_toml(repo_dir):
				counts['skipped_devel_no_pyproject'] += 1
				skipped_devel_no_pyproject_by_file[filename] += 1
				if args.dry_run:
					print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} skip {filename} (no pyproject.toml) in {repo_dir}")
				continue

			source_file = devel_source_map[filename]
			dest_file = os.path.join(devel_dir, filename)

			if os.path.abspath(dest_file) == source_file:
				counts['skipped_source_devel'] += 1
				if not args.dry_run:
					print(f"{Colors.CYAN}[SKIP SOURCE]{Colors.RESET} {dest_file}")
				continue

			try:
				dest_exists = os.path.isfile(dest_file)
				is_same = False
				if dest_exists:
					is_same = filecmp.cmp(source_file, dest_file, shallow=False)
				if is_same:
					counts['skipped_same_devel'] += 1
					skipped_same_devel_by_file[filename] += 1
					continue

				if args.dry_run:
					action = 'update' if dest_exists else 'copy'
					print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} {action} {source_file} -> {dest_file}")
				else:
					shutil.copy2(source_file, dest_file)
				if dest_exists:
					counts['updated_devel'] += 1
					updated_devel_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[UPDATED]{Colors.RESET} {source_file} -> {dest_file}")
				else:
					counts['copied_devel'] += 1
					copied_devel_by_file[filename] += 1
					if not args.dry_run:
						print(f"{Colors.BLUE}[COPIED]{Colors.RESET} {source_file} -> {dest_file}")
			except Exception as e:
				counts['errors'] += 1
				print(f"{Colors.RED}[ERROR]{Colors.RESET} {repo_dir}: {e}")

		agents_path = os.path.join(repo_dir, 'AGENTS.md')
		try:
			style_paths = {
				filename: os.path.relpath(
					os.path.join(dest_dir, filename),
					repo_dir
				)
				for filename in styles
			}
			was_existing = os.path.exists(agents_path)
			changed = ensure_agents_file(
				agents_path,
				style_paths,
				args.dry_run,
			)
			if changed:
				if args.dry_run:
					if was_existing:
						print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} append AGENTS.md guidance block to {agents_path}")
					else:
						print(f"{Colors.YELLOW}[DRY RUN]{Colors.RESET} create {agents_path}")
				if was_existing:
					counts['updated_agents'] += 1
				else:
					counts['created_agents'] += 1
		except Exception as e:
			counts['errors'] += 1
			print(f"{Colors.RED}[ERROR]{Colors.RESET} {repo_dir}: {e}")

	summary = {
		'context': {
			'base_dir': base_dir,
			'source_dir': source_dir,
		},
		'skipped': {
			'metrics': [
				{
					'label': 'Skipped (same)',
					'value': counts['skipped_same'],
					'expected': COUNTER_EXPECTED['skipped_same'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'Skipped (source)',
					'value': counts['skipped_source'],
					'expected': COUNTER_EXPECTED['skipped_source'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'Skipped (non-repo)',
					'value': counts['skipped_non_repo'],
					'expected': COUNTER_EXPECTED['skipped_non_repo'],
					'always_color': Colors.YELLOW,
				},
				{
					'label': 'tests scripts skipped (same)',
					'value': counts['skipped_same_tests'],
					'expected': COUNTER_EXPECTED['skipped_same_tests'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'tests scripts skipped (source)',
					'value': counts['skipped_source_tests'],
					'expected': COUNTER_EXPECTED['skipped_source_tests'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'tests scripts skipped (no python)',
					'value': counts['skipped_tests_no_python'],
					'expected': COUNTER_EXPECTED['skipped_tests_no_python'],
					'always_color': Colors.YELLOW,
				},
				{
					'label': 'devel scripts skipped (same)',
					'value': counts['skipped_same_devel'],
					'expected': COUNTER_EXPECTED['skipped_same_devel'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'devel scripts skipped (source)',
					'value': counts['skipped_source_devel'],
					'expected': COUNTER_EXPECTED['skipped_source_devel'],
					'always_color': Colors.GREEN,
				},
				{
					'label': 'devel scripts skipped (no pyproject.toml)',
					'value': counts['skipped_devel_no_pyproject'],
					'expected': COUNTER_EXPECTED['skipped_devel_no_pyproject'],
					'always_color': Colors.YELLOW,
				},
			],
			'by_file': [
				{
					'title': 'Skipped (same) by file:',
					'filenames': styles,
					'counts': skipped_same_by_file,
					'always_color': Colors.GREEN,
				},
				{
					'title': 'Skipped (same) tests scripts:',
					'filenames': test_scripts,
					'counts': skipped_same_tests_by_file,
					'always_color': Colors.GREEN,
				},
				{
					'title': 'Skipped (no python) tests scripts:',
					'filenames': test_scripts,
					'counts': skipped_tests_no_python_by_file,
					'always_color': Colors.YELLOW,
				},
				{
					'title': 'Skipped (same) devel scripts:',
					'filenames': devel_scripts,
					'counts': skipped_same_devel_by_file,
					'always_color': Colors.GREEN,
				},
				{
					'title': 'Skipped (no pyproject.toml) devel scripts:',
					'filenames': devel_scripts,
					'counts': skipped_devel_no_pyproject_by_file,
					'always_color': Colors.YELLOW,
				},
			],
		},
		'errors': counts['errors'],
		'changes': {
			'metrics': [
				{
					'label': 'Git perms updated',
					'value': counts['git_perms_changed'],
					'expected': COUNTER_EXPECTED['git_perms_changed'],
					'always_color': Colors.BLUE,
				},
				{
					'label': 'Git perms unchanged',
					'value': counts['git_perms_unchanged'],
					'expected': COUNTER_EXPECTED['git_perms_unchanged'],
					'always_color': Colors.GREEN,
				},
				{
					'label': '.gitignore created',
					'value': counts['gitignore_created'],
					'expected': COUNTER_EXPECTED['gitignore_created'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore updated',
					'value': counts['gitignore_updated'],
					'expected': COUNTER_EXPECTED['gitignore_updated'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore lines added',
					'value': counts['gitignore_lines_added'],
					'expected': COUNTER_EXPECTED['gitignore_lines_added'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore cleaned',
					'value': counts['gitignore_cleaned'],
					'expected': COUNTER_EXPECTED['gitignore_cleaned'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore duplicates removed',
					'value': counts['gitignore_duplicates_removed'],
					'expected': COUNTER_EXPECTED['gitignore_duplicates_removed'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore whitespace cleaned',
					'value': counts['gitignore_whitespace_cleaned'],
					'expected': COUNTER_EXPECTED['gitignore_whitespace_cleaned'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore deprecated entries removed',
					'value': counts['gitignore_deprecated_removed'],
					'expected': COUNTER_EXPECTED['gitignore_deprecated_removed'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': '.gitignore deprecated lines removed',
					'value': counts['gitignore_deprecated_entries_removed'],
					'expected': COUNTER_EXPECTED['gitignore_deprecated_entries_removed'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'tests scripts copied',
					'value': counts['copied_tests'],
					'expected': COUNTER_EXPECTED['copied_tests'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'tests scripts updated',
					'value': counts['updated_tests'],
					'expected': COUNTER_EXPECTED['updated_tests'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'tests deprecated scripts removed',
					'value': counts['removed_deprecated_tests'],
					'expected': COUNTER_EXPECTED['removed_deprecated_tests'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'tests/ created',
					'value': counts['created_tests_dirs'],
					'expected': COUNTER_EXPECTED['created_tests_dirs'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'tests/conftest.py created',
					'value': counts['created_conftest'],
					'expected': COUNTER_EXPECTED['created_conftest'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'devel/ created',
					'value': counts['created_devel_dirs'],
					'expected': COUNTER_EXPECTED['created_devel_dirs'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'docs/CHANGELOG.md created',
					'value': counts['created_changelog'],
					'expected': COUNTER_EXPECTED['created_changelog'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'AGENTS.md created',
					'value': counts['created_agents'],
					'expected': COUNTER_EXPECTED['created_agents'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'AGENTS.md lines added',
					'value': counts['updated_agents'],
					'expected': COUNTER_EXPECTED['updated_agents'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'Copied',
					'value': counts['copied'],
					'expected': COUNTER_EXPECTED['copied'],
					'positive_color': Colors.BLUE,
				},
				{
					'label': 'Updated',
					'value': counts['updated'],
					'expected': COUNTER_EXPECTED['updated'],
					'positive_color': Colors.BLUE,
				},
			],
			'by_file': [
				{
					'title': 'Style guides copied by file:',
					'filenames': styles,
					'counts': copied_by_file,
					'positive_color': Colors.BLUE,
				},
				{
					'title': 'Style guides updated by file:',
					'filenames': styles,
					'counts': updated_by_file,
					'positive_color': Colors.BLUE,
				},
				{
					'title': 'Tests scripts copied by file:',
					'filenames': test_scripts,
					'counts': copied_tests_by_file,
					'positive_color': Colors.BLUE,
				},
				{
					'title': 'Tests scripts updated by file:',
					'filenames': test_scripts,
					'counts': updated_tests_by_file,
					'positive_color': Colors.BLUE,
				},
				{
					'title': 'Devel scripts copied by file:',
					'filenames': devel_scripts,
					'counts': copied_devel_by_file,
					'positive_color': Colors.BLUE,
				},
				{
					'title': 'Devel scripts updated by file:',
					'filenames': devel_scripts,
					'counts': updated_devel_by_file,
					'positive_color': Colors.BLUE,
				},
			],
		},
	}
	print_summary_report(summary)


#============================================
if __name__ == '__main__':
	main()
