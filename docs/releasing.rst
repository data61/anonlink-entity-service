
Releasing
=========

Releasing a version of the Anonlink Entity Service
--------------------------------------------------

We follow gitflow. Each release has a GitHub milestone associated with it which groups all the features and
bug fixes together.

- Create a branch off the latest ``develop`` called ``release-x.y.z``
- Update the versions in the code base of any components that have been changed e.g. ``backend/entityservice/VERSION``.
- Update the changelog to include user friendly information on all features, taking special care
  to mention any breaking changes.
- Open a PR to merge these changes into ``develop``, and get a code review. Make any requested changes, and merge the
  changes into ``develop`` (don't close the branch).
- Open a PR to merge the release branch into ``master``, hopefully the CI tests all pass. Merge, rather than
  squashing the commits.
- Create a git tag of the form ``vX.Y.Z[-aN|-bN]`` (e.g. using GitHub's releases ui)
- Push release versions of docker images from this tag (manually for now but ideally using CI)
- Commit to develop (via a PR) creating a new ``"Next Version`` section in the changelog.
