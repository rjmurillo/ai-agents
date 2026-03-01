#!/usr/bin/env python3
"""Add a reply to a GitHub PR review thread using GraphQL.

Posts a reply to a review thread using the thread ID (PRRT_...).
Optionally resolves the thread after posting the reply.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Thread not found / file not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    write_error_and_exit,
)

REPLY_MUTATION = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment {
      id
      databaseId
      url
      createdAt
      author { login }
    }
  }
}
"""

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Add reply to PR review thread")
    parser.add_argument("--thread-id", required=True, help="GraphQL thread ID (PRRT_...)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", help="Reply text")
    group.add_argument("--body-file", help="Path to file containing reply")
    parser.add_argument("--resolve", action="store_true", help="Resolve thread after reply")
    args = parser.parse_args()

    if not args.thread_id.startswith("PRRT_"):
        write_error_and_exit("Thread ID must start with 'PRRT_'", 1)

    assert_gh_authenticated()

    body = args.body
    if args.body_file:
        if not os.path.exists(args.body_file):
            write_error_and_exit(f"Body file not found: {args.body_file}", 2)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()

    if not body or not body.strip():
        write_error_and_exit("Body cannot be empty", 1)

    try:
        data = gh_graphql(REPLY_MUTATION, {"threadId": args.thread_id, "body": body})
    except Exception as e:
        if "Could not resolve" in str(e):
            write_error_and_exit(f"Thread {args.thread_id} not found", 2)
        write_error_and_exit(f"Failed to post thread reply: {e}", 3)

    comment = data.get("addPullRequestReviewThreadReply", {}).get("comment")
    if not comment:
        write_error_and_exit("Reply may not have been posted successfully", 3)

    thread_resolved = False
    if args.resolve:
        try:
            resolve_data = gh_graphql(RESOLVE_MUTATION, {"threadId": args.thread_id})
            resolve_thread = resolve_data.get("resolveReviewThread", {})
            thread_resolved = resolve_thread.get("thread", {}).get("isResolved", False)
        except Exception as e:
            print(f"Warning: Thread reply posted but failed to resolve: {e}", file=sys.stderr)

    output = {
        "Success": True,
        "ThreadId": args.thread_id,
        "CommentId": comment.get("databaseId"),
        "CommentNodeId": comment.get("id"),
        "HtmlUrl": comment.get("url"),
        "CreatedAt": comment.get("createdAt"),
        "Author": comment.get("author", {}).get("login") if comment.get("author") else None,
        "ThreadResolved": thread_resolved,
    }

    print(json.dumps(output, indent=2))
    print(f"Posted reply to thread {args.thread_id}", file=sys.stderr)
    print(f"  Comment ID: {output['CommentId']}", file=sys.stderr)
    print(f"  URL: {output['HtmlUrl']}", file=sys.stderr)
    if args.resolve:
        status = "Yes" if thread_resolved else "Failed"
        print(f"  Resolved: {status}", file=sys.stderr)


if __name__ == "__main__":
    main()
