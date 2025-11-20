"""Command-line interface for reddit_downloader."""

import argparse
import sys
from pathlib import Path

from reddit_downloader.client import RedditClient
from reddit_downloader.downloader import MediaDownloader
from reddit_downloader.parser import parse_url
from reddit_downloader.types import URLType


def download_post(
    url: str,
    output_dir: Path,
    client: RedditClient,
    verbose: bool = False,
) -> int:
    """Download media from a single Reddit post.

    Args:
        url: Reddit post URL
        output_dir: Directory to save media
        client: Reddit API client
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parsed = parse_url(url)

    if parsed["url_type"] != URLType.POST:
        print(f"Error: Invalid post URL: {url}", file=sys.stderr)
        return 1

    post_id = parsed["post_id"]
    if not post_id:
        print(f"Error: Could not extract post ID from URL: {url}", file=sys.stderr)
        return 1

    try:
        if verbose:
            print(f"Fetching post {post_id}...")

        post = client.get_post(post_id)
        downloader = MediaDownloader(output_dir, verbose=verbose)

        if verbose:
            print(f"Downloading media from: {post.title}")

        results = downloader.download_post_media(post)

        if not results:
            print("No media found in post")
            return 0

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count

        if verbose or fail_count > 0:
            print("\nDownload complete:")
            print(f"  Successful: {success_count}")
            print(f"  Failed: {fail_count}")

        for result in results:
            if result.success and result.file_path:
                print(f"Downloaded: {result.file_path}")
            elif not result.success and verbose:
                print(f"Failed: {result.error}")

        return 0 if fail_count == 0 else 1

    except Exception as e:
        print(f"Error downloading post: {e}", file=sys.stderr)
        return 1


def download_user(
    username: str,
    output_dir: Path,
    client: RedditClient,
    limit: int | None = None,
    verbose: bool = False,
) -> int:
    """Download media from all posts by a user.

    Args:
        username: Reddit username
        output_dir: Directory to save media
        client: Reddit API client
        limit: Maximum number of posts to process
        verbose: Enable verbose output

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        if verbose:
            print(f"Fetching posts from user: {username}")
            if limit:
                print(f"Limit: {limit} posts")

        downloader = MediaDownloader(output_dir, verbose=verbose)
        posts = client.get_user_posts(username, limit=limit)

        total_posts = 0
        total_downloads = 0
        total_failures = 0

        for post in posts:
            total_posts += 1

            if verbose:
                print(f"\n[{total_posts}] {post.title}")

            results = downloader.download_post_media(post)

            for result in results:
                if result.success:
                    total_downloads += 1
                    if result.file_path:
                        print(f"  Downloaded: {result.file_path}")
                else:
                    total_failures += 1
                    if verbose and result.error:
                        print(f"  Failed: {result.error}")

        print("\n=== Summary ===")
        print(f"Posts processed: {total_posts}")
        print(f"Files downloaded: {total_downloads}")
        print(f"Failed downloads: {total_failures}")

        return 0

    except Exception as e:
        print(f"Error downloading from user: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Download media from Reddit posts and user profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Post command
    post_parser = subparsers.add_parser("post", help="Download from a single post")
    post_parser.add_argument("url", help="Reddit post URL")
    post_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Output directory (default: downloads)",
    )
    post_parser.add_argument(
        "--client-id",
        help="Reddit API client ID (or set REDDIT_CLIENT_ID env var)",
    )
    post_parser.add_argument(
        "--client-secret",
        help="Reddit API client secret (or set REDDIT_CLIENT_SECRET env var)",
    )
    post_parser.add_argument(
        "--user-agent",
        help="Reddit API user agent (or set REDDIT_USER_AGENT env var)",
    )
    post_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # User command
    user_parser = subparsers.add_parser("user", help="Download from a user's posts")
    user_parser.add_argument("username", help="Reddit username or user profile URL")
    user_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Output directory (default: downloads)",
    )
    user_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        help="Maximum number of posts to process",
    )
    user_parser.add_argument(
        "--client-id",
        help="Reddit API client ID (or set REDDIT_CLIENT_ID env var)",
    )
    user_parser.add_argument(
        "--client-secret",
        help="Reddit API client secret (or set REDDIT_CLIENT_SECRET env var)",
    )
    user_parser.add_argument(
        "--user-agent",
        help="Reddit API user agent (or set REDDIT_USER_AGENT env var)",
    )
    user_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # Web command
    web_parser = subparsers.add_parser("web", help="Start web interface")
    web_parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=5000,
        help="Port for web server (default: 5000)",
    )
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address for web server (default: 127.0.0.1)",
    )
    web_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="Output directory (default: downloads)",
    )
    web_parser.add_argument(
        "--client-id",
        help="Reddit API client ID (or set REDDIT_CLIENT_ID env var)",
    )
    web_parser.add_argument(
        "--client-secret",
        help="Reddit API client secret (or set REDDIT_CLIENT_SECRET env var)",
    )
    web_parser.add_argument(
        "--user-agent",
        help="Reddit API user agent (or set REDDIT_USER_AGENT env var)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Handle web command separately (will import web module only when needed)
    if args.command == "web":
        try:
            from reddit_downloader.web.app import run_web_server

            return run_web_server(
                host=args.host,
                port=args.port,
                output_dir=args.output,
                client_id=args.client_id,
                client_secret=args.client_secret,
                user_agent=args.user_agent,
            )
        except ImportError as e:
            print(f"Error: Web interface not available: {e}", file=sys.stderr)
            return 1

    # Initialize Reddit client for post/user commands
    try:
        client = RedditClient(
            client_id=args.client_id,
            client_secret=args.client_secret,
            user_agent=args.user_agent,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Handle post command
    if args.command == "post":
        return download_post(
            url=args.url,
            output_dir=args.output,
            client=client,
            verbose=args.verbose,
        )

    # Handle user command
    elif args.command == "user":
        # Check if username is a URL
        username = args.username
        if "reddit.com" in username:
            parsed = parse_url(username)
            if parsed["url_type"] == URLType.USER and parsed["username"]:
                username = parsed["username"]
            else:
                print(f"Error: Invalid user URL: {username}", file=sys.stderr)
                return 1

        return download_user(
            username=username,
            output_dir=args.output,
            client=client,
            limit=args.limit,
            verbose=args.verbose,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
