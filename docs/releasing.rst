
Releasing
=========

Releasing a version of the Anonlink Entity Service
--------------------------------------------------

We follow gitflow. Each release has a GitHub milestone associated with it which groups all the features and
bug fixes together.

Multiple docker images are contained within this repository (e.g., ``backend``, ``frontend``, ``benchmark``) which
are independently versioned. In general a release involves a new version of both the ``backend`` and the ``frontend``.
This is because the documentation is baked into the frontend so user visible changes to the backend require a new
frontend.

- Choose a new version using semantic versioning.
- Create a branch off the latest ``develop`` called ``release-x.y.z``.
- Update the versions in the code base (e.g., ``backend/entityservice/VERSION``) of any components that have been
  changed. As above note if the backend version has changed you must release a new frontend too.
- Update the versions in the Chart.yaml file.
- Update the changelog to include user friendly information on all features, taking special care
  to mention any breaking changes.
- Open a PR to merge these changes into ``develop``, and get a code review. Make any requested changes, and merge the
  changes into ``develop`` (don't close the branch).
- Open a PR to merge the release branch into ``master``, only proceed if the CI tests all pass. Merge, rather than
  squashing the commits.
- Create a git tag of the form ``vX.Y.Z[-aN|-bN]`` (e.g. using GitHub's releases ui).
- Tag and push release versions of docker images from this tag and the tag `latest` (manually for now but ideally using CI).
- Commit to develop (via a PR) creating a new ``"Next Version`` section in the changelog.
- Proudly announce the new release on the anonlink google group https://groups.google.com/forum/#!forum/anonlink

