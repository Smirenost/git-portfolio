"""Command-line interface."""
import logging
import sys
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

import github
import requests

import git_portfolio.config_manager as config_manager
import git_portfolio.prompt as prompt

# starting log
FORMAT = "%(asctime)s %(message)s"
DATE_FORMAT = "%d/%m/%Y %H:%M:%S"
logging.basicConfig(level=logging.ERROR, format=FORMAT, datefmt=DATE_FORMAT)
LOGGER = logging.getLogger(__name__)


class GithubManager:
    def __init__(self):
        self.config_manager = config_manager.ConfigManager()
        self.configs = self.config_manager.load_configs()
        if self.configs.github_access_token:
            self.github_setup()
        else:
            self.init_config()

    def create_issues(self, issue: Optional[prompt.Issue] = None) -> None:
        if not issue:
            issue = prompt.create_issues(self.configs.github_selected_repos)
        labels = (
            [label.strip() for label in issue.labels.split(",")] if issue.labels else []
        )
        for github_repo in self.configs.github_selected_repos:
            repo = self.github_connection.get_repo(github_repo)
            try:
                repo.create_issue(title=issue.title, body=issue.body, labels=labels)
                print("{}: issue created successfully.".format(github_repo))
            except github.GithubException as github_exception:
                if (
                    github_exception.data["message"]
                    == "Issues are disabled for this repo"
                ):
                    print(
                        "{}: {}. It may be a fork.".format(
                            github_repo, github_exception.data["message"]
                        )
                    )
                else:
                    print(
                        "{}: {}.".format(github_repo, github_exception.data["message"])
                    )

    def create_pull_requests(self, pr: Optional[prompt.PullRequest] = None) -> None:
        if not pr:
            pr = prompt.create_pull_requests(self.configs.github_selected_repos)

        for github_repo in self.configs.github_selected_repos:
            repo = self.github_connection.get_repo(github_repo)
            body = pr.body
            labels = (
                set(label.strip() for label in pr.labels.split(","))
                if pr.labels
                else set()
            )
            # link issues
            if pr.confirmation:
                issues = repo.get_issues(state="open")
                closes = ""
                for issue in issues:
                    if pr.link in issue.title:
                        closes += "#{} ".format(issue.number)
                        if pr.inherit_labels:
                            issue_labels = [label.name for label in issue.get_labels()]
                            labels.update(issue_labels)
                closes = closes.strip()
                if closes:
                    body += "\n\nCloses {}".format(closes)
            try:
                pr = repo.create_pull(
                    title=pr.title,
                    body=body,
                    head=pr.head,
                    base=pr.base,
                    draft=pr.draft,
                )
                print("{}: PR created successfully.".format(github_repo))
                # PyGithub does not support a list of strings for adding (only one str)
                for label in labels:
                    pr.add_to_labels(label)
            except github.GithubException as github_exception:
                extra = ""
                for error in github_exception.data["errors"]:
                    if "message" in error:
                        extra += "{} ".format(error["message"])
                    else:
                        extra += "Invalid field {}. ".format(error["field"])
                print(
                    "{}: {}. {}".format(
                        github_repo, github_exception.data["message"], extra
                    )
                )

    def merge_pull_requests(
        self, pr_merge: Optional[prompt.PullRequestMerge] = None
    ) -> None:
        """Merge pull request."""
        if not pr_merge:
            pr_merge = prompt.merge_pull_requests(
                self.github_username, self.configs.github_selected_repos
            )
        # Important note: base and head arguments have different import formats.
        # https://developer.github.com/v3/pulls/#list-pull-requests
        # head needs format "user/org:branch"
        head = "{}:{}".format(pr_merge.prefix, pr_merge.head)
        state = "open"

        for github_repo in self.configs.github_selected_repos:
            repo = self.github_connection.get_repo(github_repo)
            pulls = repo.get_pulls(state=state, base=pr_merge.base, head=head)
            if pulls.totalCount == 1:
                pull = pulls[0]
                if pull.mergeable:
                    try:
                        pull.merge()
                        print("{}: PR merged successfully.".format(github_repo))
                    except github.GithubException as github_exception:
                        print(
                            "{}: {}.".format(
                                github_repo, github_exception.data["message"]
                            )
                        )
                else:
                    print(
                        "{}: PR not mergeable, GitHub checks may be running.".format(
                            github_repo
                        )
                    )
            else:
                print(
                    "{}: no open PR found for {}:{}.".format(
                        github_repo, pr_merge.base, pr_merge.head
                    )
                )

    def delete_branches(self, branch="") -> None:
        if not branch:
            branch = prompt.delete_branches(self.configs.github_selected_repos)

        for github_repo in self.configs.github_selected_repos:
            repo = self.github_connection.get_repo(github_repo)
            try:
                git_ref = repo.get_git_ref("heads/{}".format(branch))
                git_ref.delete()
                print("{}: branch deleted successfully.".format(github_repo))
            except github.GithubException as github_exception:
                print("{}: {}.".format(github_repo, github_exception.data["message"]))

    def get_github_connection(self) -> github.Github:
        # GitHub Enterprise
        if self.configs.github_hostname:
            base_url = "https://{}/api/v3".format(self.configs.github_hostname)
            return github.Github(
                base_url=base_url, login_or_token=self.configs.github_access_token
            )
        # GitHub.com
        return github.Github(self.configs.github_access_token)

    def get_github_username(
        self,
        user: Union[
            github.AuthenticatedUser.AuthenticatedUser, github.NamedUser.NamedUser
        ],
    ) -> str:
        try:
            return user.login
        except (github.BadCredentialsException, github.GithubException):
            print("Wrong GitHub token/permissions. Please try again.")
            self.init_config()
        except requests.exceptions.ConnectionError:
            sys.exit("Unable to reach server. Please check you network.")

    def get_github_repos(
        self,
        user: Union[
            github.AuthenticatedUser.AuthenticatedUser, github.NamedUser.NamedUser
        ],
    ) -> github.PaginatedList.PaginatedList:
        return user.get_repos()

    def select_github_repos(self) -> None:
        if self.configs.github_selected_repos:
            print("\nThe configured repos will be used:")
            for repo in self.configs.github_selected_repos:
                print(" *", repo)
            new_repos = prompt.new_repos()
            if not new_repos:
                print("gitp successfully configured.")
                return

        try:
            repo_names = [repo.full_name for repo in self.github_repos]
        except Exception as ex:
            print(ex)

        self.configs.github_selected_repos = prompt.select_repos(repo_names)
        self.config_manager.save_configs(self.configs)
        print("gitp successfully configured.")

    def github_setup(self) -> None:
        self.github_connection = self.get_github_connection()
        user = self.github_connection.get_user()
        self.github_username = self.get_github_username(user)
        self.github_repos = self.get_github_repos(user)

    def init_config(self) -> None:
        answers = prompt.connect_github(self.configs.github_access_token)
        self.configs.github_access_token = answers.github_access_token.strip()
        self.configs.github_hostname = answers.github_hostname
        self.github_setup()
        self.select_github_repos()
