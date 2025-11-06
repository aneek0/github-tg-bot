from typing import Dict, Any, List, Optional
from aiogram import html
from bot.utils.constants import BODY_PREVIEW_LENGTH, RELEASE_BODY_PREVIEW_LENGTH


def format_commit_message(
    repo_full_name: str,
    branch: str,
    commits: List[Dict[str, Any]],
    compare_url: Optional[str] = None
) -> str:
    """Форматирует сообщение о коммитах"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    
    text = f"🔧 On {html.link(f'{owner}/{repo}', repo_url)}:{html.code(branch)} new commits!\n"
    text += f"{html.bold(f'{len(commits)} commits pushed.')}\n"
    
    if compare_url:
        text += f"Compare changes: {html.link('Compare changes', compare_url)}\n\n"
    
    for commit in commits:
        sha = commit.get("sha", "")[:7]
        author = commit.get("author", {})
        commit_author = author.get("login", "Unknown")
        commit_author_name = author.get("name", commit_author)
        message = commit.get("commit", {}).get("message", "").split("\n")[0]
        
        commit_url = f"{repo_url}/commit/{commit.get('sha', '')}"
        author_url = f"https://github.com/{commit_author}" if commit_author != "Unknown" else None
        
        if author_url:
            text += f"┃ Commit {html.code(f'#{sha}')} by {html.link(commit_author_name, author_url)}\n"
        else:
            text += f"┃ Commit {html.code(f'#{sha}')} by {html.bold(commit_author_name)}\n"
        text += f"┃ {html.link(message, commit_url)}\n"
        
        # Добавляем информацию о файлах если есть
        stats = commit.get("stats", {})
        if stats:
            additions = stats.get("additions", 0)
            deletions = stats.get("deletions", 0)
            if additions > 0 or deletions > 0:
                text += f"┃ Diff: {html.code(f'+ {additions}')} {html.code(f'- {deletions}')}\n"
        
        text += "\n"
    
    return text


def format_star_message(
    repo_full_name: str,
    user_login: Optional[str],
    user_name: Optional[str],
    total_stars: int
) -> str:
    """Форматирует сообщение о новой звезде"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    
    text = f"⭐ On {html.code(f'{owner}/{repo}')} added star!\n\n"
    text += f"Total stars: {html.bold(str(total_stars))}\n"
    
    if user_login:
        user_display = user_name or user_login
        text += f"User: {html.code(f'@{user_login}')}"
    
    return text


def format_fork_message(
    repo_full_name: str,
    fork_owner: str,
    fork_full_name: str
) -> str:
    """Форматирует сообщение о форке"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    fork_url = f"https://github.com/{fork_full_name}"
    
    text = f"🍴 On {html.code(f'{owner}/{repo}')} new fork!\n\n"
    text += f"Forked by: {html.code(f'@{fork_owner}')}\n"
    text += f"Fork: {html.link(fork_full_name, fork_url)}"
    
    return text


def format_issue_message(
    repo_full_name: str,
    action: str,
    issue: Dict[str, Any]
) -> str:
    """Форматирует сообщение об issue"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    issue_number = issue.get("number", 0)
    issue_url = issue.get("html_url", f"{repo_url}/issues/{issue_number}")
    
    action_icons = {
        "opened": "📝",
        "closed": "✅"
    }
    
    icon = action_icons.get(action, "📝")
    user = issue.get("user", {})
    user_login = user.get("login", "Unknown")
    title = issue.get("title", "")
    body = issue.get("body", "")
    
    text = f"{icon} On {html.code(f'{owner}/{repo}')} {action} issue!\n\n"
    text += f"📄 {html.bold(title)}\n"
    
    if body:
        # Берем первые N символов описания
        body_preview = body[:BODY_PREVIEW_LENGTH] + "..." if len(body) > BODY_PREVIEW_LENGTH else body
        text += f"{html.italic(body_preview)}\n\n"
    
    text += f"User: {html.code(f'@{user_login}')}\n"
    text += f"#{issue_number}"
    
    return text


def format_issue_comment_message(
    repo_full_name: str,
    action: str,
    comment: Dict[str, Any],
    issue: Dict[str, Any]
) -> str:
    """Форматирует сообщение о комментарии к issue"""
    owner, repo = repo_full_name.split("/", 1)
    issue_number = issue.get("number", 0)
    comment_url = comment.get("html_url", "")
    
    icon = "💬" if action == "created" else "🗑️"
    user = comment.get("user", {})
    user_login = user.get("login", "Unknown")
    body = comment.get("body", "")
    
    text = f"{icon} On {html.code(f'{owner}/{repo}')} {action} issue comment!\n\n"
    text += f"Issue #{issue_number}: {html.bold(issue.get('title', ''))}\n\n"
    
    if body:
        body_preview = body[:200] + "..." if len(body) > 200 else body
        text += f"{html.italic(body_preview)}\n\n"
    
    text += f"User: {html.code(f'@{user_login}')}"
    
    return text


def format_pull_request_message(
    repo_full_name: str,
    action: str,
    pr: Dict[str, Any]
) -> str:
    """Форматирует сообщение о pull request"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    pr_number = pr.get("number", 0)
    pr_url = pr.get("html_url", f"{repo_url}/pull/{pr_number}")
    
    action_icons = {
        "opened": "📦",
        "closed": "✅",
        "synchronize": "🔄"
    }
    
    icon = action_icons.get(action, "📦")
    user = pr.get("user", {})
    user_login = user.get("login", "Unknown")
    title = pr.get("title", "")
    body = pr.get("body", "")
    
    text = f"{icon} On {html.code(f'{owner}/{repo}')} {action} pull request!\n\n"
    
    if action == "synchronize":
        text += f"🔄 {html.bold('Немного изменений')}\n"
    else:
        text += f"📄 {html.bold(title)}\n"
    
    if body:
        # Берем первые N символов описания
        body_preview = body[:BODY_PREVIEW_LENGTH] + "..." if len(body) > BODY_PREVIEW_LENGTH else body
        text += f"{html.italic(body_preview)}\n\n"
    
    # Добавляем информацию о diff если есть
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)
    if additions > 0 or deletions > 0:
        text += f"Diff: {html.code(f'+ {additions}')} {html.code(f'- {deletions}')}\n\n"
    
    text += f"User: {html.code(f'@{user_login}')}\n"
    text += f"#{pr_number}"
    
    return text


def format_pull_request_comment_message(
    repo_full_name: str,
    action: str,
    comment: Dict[str, Any],
    pr: Dict[str, Any]
) -> str:
    """Форматирует сообщение о комментарии к pull request"""
    owner, repo = repo_full_name.split("/", 1)
    pr_number = pr.get("number", 0)
    comment_url = comment.get("html_url", "")
    
    icon = "💬" if action == "created" else "🗑️"
    user = comment.get("user", {})
    user_login = user.get("login", "Unknown")
    body = comment.get("body", "")
    
    text = f"{icon} On {html.code(f'{owner}/{repo}')} {action} pull request comment!\n\n"
    text += f"PR #{pr_number}: {html.bold(pr.get('title', ''))}\n\n"
    
    if body:
        body_preview = body[:200] + "..." if len(body) > 200 else body
        text += f"{html.italic(body_preview)}\n\n"
    
    text += f"User: {html.code(f'@{user_login}')}"
    
    return text


def format_release_message(
    repo_full_name: str,
    action: str,
    release: Dict[str, Any]
) -> str:
    """Форматирует сообщение о релизе"""
    owner, repo = repo_full_name.split("/", 1)
    repo_url = f"https://github.com/{owner}/{repo}"
    release_url = release.get("html_url", "")
    
    icon = "🚀"
    tag_name = release.get("tag_name", "")
    name = release.get("name", tag_name)
    body = release.get("body", "")
    author = release.get("author", {})
    user_login = author.get("login", "Unknown")
    
    text = f"{icon} On {html.code(f'{owner}/{repo}')} {action} release!\n\n"
    text += f"🏷️ {html.bold(name)}\n"
    
    if body:
        body_preview = body[:RELEASE_BODY_PREVIEW_LENGTH] + "..." if len(body) > RELEASE_BODY_PREVIEW_LENGTH else body
        text += f"{html.italic(body_preview)}\n\n"
    
    text += f"User: {html.code(f'@{user_login}')}"
    
    return text


def format_stats_message(
    stats: Dict[str, Dict[str, Any]],
    user_repos: Dict[str, Dict[str, Any]]
) -> str:
    """Форматирует сообщение со статистикой"""
    if not stats:
        return "📊 Статистика пока недоступна."
    
    text = "📊 Статистика по репозиториям:\n\n"
    
    for repo_key, repo_data in user_repos.items():
        owner, repo = repo_key.split("/", 1)
        repo_url = f"https://github.com/{owner}/{repo}"
        repo_stats = stats.get(repo_key, {})
        
        text += f"🔗 {html.link(repo_key, repo_url)}\n"
        text += f"⭐ Stars: {html.bold(str(repo_stats.get('stars', 0)))}\n"
        text += f"🍴 Forks: {html.bold(str(repo_stats.get('forks', 0)))}\n"
        
        # Issues
        issues_data = repo_stats.get("issues", {})
        if isinstance(issues_data, dict):
            issues_open = issues_data.get("open", 0)
            issues_closed = issues_data.get("closed", 0)
            text += f"📝 Issues: {html.bold(f'{issues_open} open, {issues_closed} closed')}\n"
        else:
            text += f"📝 Issues: {html.bold(str(issues_data))}\n"
        
        # Pull Requests
        prs_data = repo_stats.get("pull_requests", {})
        if isinstance(prs_data, dict):
            prs_open = prs_data.get("open", 0)
            prs_closed = prs_data.get("closed", 0)
            text += f"📦 Pull Requests: {html.bold(f'{prs_open} open, {prs_closed} closed')}\n"
        else:
            text += f"📦 Pull Requests: {html.bold(str(prs_data))}\n"
        
        # Языки
        languages = repo_stats.get("languages", {})
        if languages:
            # Сортируем по количеству байт кода
            sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
            langs_list = ", ".join([f"{lang} ({size // 1024}KB)" for lang, size in sorted_langs])
            text += f"💻 Languages: {html.code(langs_list)}\n"
        
        # Дата обновления
        last_updated = repo_stats.get("last_updated")
        if last_updated:
            text += f"🕐 Last updated: {html.code(last_updated[:10])}\n"
        
        text += "\n"
    
    return text

