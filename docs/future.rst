

Road map for the entity service
===============================

- baseline benchmarking vs known datasets (accuracy and speed) e.g ``recordspeed`` datasets
- blocking
- Schema specification and tooling
- Algorithmic improvements. e.g., implementing canopy clustering solver
- A web front end including authentication and access control
- Uploading multiple hashes per entity. Handle multiple schemas.
- Check how we deal with missing information, old addresses etc
- Semi supervised machine learning methods to learn thresholds
- Handle 1 to many relationships. E.g. familial groups
- Larger scale graph solving methods
- Remove bottleneck of sparse links having to fit in redis.
- improve uploads by allowing direct binary file transfer into object store
- optimise anonlink memory management and C++ code

Bigger Projects

- GPU implementation of core similarity scoring
- somewhat homomorphic encryption could be used for similarity score
- consider allowing users to upload raw PII

