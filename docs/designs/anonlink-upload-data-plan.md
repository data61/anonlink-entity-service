# Add data pull feature to Anonlink Entity Service

Author: Brian Thorne
Status: Draft
Created: 2020-03-31
Updated: 2020-04-06

## Abstract/Purpose

In early 2020 blocking has been added to increase the capacity of the Anonlink system, however the system cannot 
currently handle users uploading large encoded datasets in a reliable way. Investing in scaling Anonlink to a system
that can deal with tens of millions of records vastly increases the chance of adoption and the general usefulness of 
the system. 

When a client tries to upload tens of millions of records today they must have a fast and reliable internet connection
and complete in one REST call the entire data upload operation. These uploads can easily be multiple GiB of data.

On the server side we have had to increase default timeouts to >60s to handle the upload of single digit millions
of encoded records. The idea of the pull feature is to allow the client to point to a location where the data can be
pulled by the server. Modifying the client and API to upload in chunks - making many smaller upload requests - was also
considered. This alternative was rejected as we estimate it would take more effort to get to the same reliability. For
example the chunking, compression, retrying, and data integrity would all have to be custom handled.

With the Anonlink system we aim to provide everything required to take users from clean records through to an accurate
concordance table. We rejected the idea of requiring a data provider to setup their own object store or otherwise
hosting their encoded data online; instead we will modify the client to be able to upload to an object store.

Not including the initial design, implementation is expected to be approximately 2 sprints of work for 2 software 
engineers. The high level objective is that Anonlink be usable to link between datasets that are roughly the size of 
the Australian population. 

The aim of the rest of this document is to specify the design of the "pull data" feature.

The sections are:

- Requirements
- High level system design
- Specifications for implementation (including the REST API).
- decisions and alternatives considered. What would be the "best"/"easiest" approach.

## User Stories

- As a user with a multi-gigabyte dataset on my machine and a slow, intermittent NBN internet connection, I want my upload
  to happen as quickly and smoothly as possible.

- As a user with an encoded dataset already available in an S3 bucket, I want Anonlink to fetch it directly so I don't 
  have to download and then upload it.

## Requirements

- A user shall be able to point to data in an object store instead of directly uploading to Anonlink.
- A user may be able to point to data via a http URL instead of directly uploading to Anonlink.
- The system shall provide a mechanism to grant temporary & restricted object store credentials.
- The system shall accept uploads of up to 1TiB of data.
- In the event of an upload being interrupted, a user shall be able to resume the upload at a later stage without 
  having to re-upload data already sent.
- The system shall provide an option to expose the MinIO object store.
- The client tool shall not share users object store credentials with the service without explicit direction.
- The client tool shall support uploading to the service's object store.
- The client tool may support uploading to an external object store.


## High Level Design

The Anonlink Entity Service already relies on MinIO (or AWS S3) as an ancillary services for storing encoding data
as well as data for in progress computations. MinIO can easily and robustly handle the expected volume of data, and we 
will leverage the object store to support this pull feature.

At deployment time the user will have the option of exposing the MinIO object store used by the Anonlink Entity Service,
or - as already supported - providing external S3/MinIO access credentials. The Anonlink Entity Service's API will be
modified such that a data provider can request temporary object store credentials. The client uses these temporary
credentials to upload their encodings to the object store. The client then informs the Anonlink server via the `clks` endpoint
of the object store address of the encodings. As per current behaviour, the client would be given an upload token and the normal
linkage process continues. 

![](../_static/data_upload_sequence.png)


This entire process would all be transparent to the data provider using `anonlink-client`; internally the client would wrap 
an S3 or MinIO client library.


## Specifications

### Rest API

#### Modification to the upload endpoint

The REST endpoint `/projects/{project_id}/clks` will be modified to take **external** data. External data is simply a
file stored in an object store. Access credentials are optionally part of the payload to support an external
object store, e.g. if the encodings are stored/uploaded to AWS S3.

External data can currently include:
- Binary encodings

A future extension may introduce a binary format for blocking info.

The additional schema for the endpoint is designed to become the default. Unlike the current `CLKnBlockUpload` format
the encodings and blocking information is split to allow for easier server side processing.

This extract from an OpenAPI specification shows a possible end state; an initial version will simply support the 
binary encoding format.

```yaml
EncodingUpload:
  description: |
    Object that contains a data provider's encodings including optional blocking information.
    Encodings, blocking information, or both can be provided as an external reference.
  type: object
  required: [encodings]
  properties:
    encodings:
      oneOf:
        - $ref: '#/EncodingArray'
        - $ref: '#/ExternalData'
    blocks:
      oneOf:
        - $ref: '#/Blocks'
        - $ref: '#/ExternalData'

ExternalData:
  description: A file in an object store.
  type: object
  required: [file]
  properties:
    credentials:
      type: object
      description: Optional credentials for the object store.
      properties:
        AccessKeyId:
          type: string
        SecretAccessKey:
          type: string
        SessionToken:
          type: string
    file:
      type: object
      required: [bucket, path]
      properties:
        endpoint:
          type: string
          description: | 
            Object store endpoint - usually a public endpoint for a MinIO as part of an Anonlink deployment e.g. 
            `minio.anonlink.easd.data61.xyz`, or a public (region specific) endpoint for AWS S3: 
            `s3.ap-southeast-2.amazonaws.com`.
          example: s3.ap-southeast-2.amazonaws.com
        bucket:
          type: string
          exapmle: anonlink-uploads
        path:
          type: string
 
Block:
  description: Blocking information for encodings. A mapping from encoding id to a list of block ids
  type: object
  additionalProperties:
    type: array
    items:
      - type: string
        description: Block ID

EncodingArray:
  description: JSON array of encodings. 
  type: array
  items:
    anyOf:
      - type: string
        format: byte
        description: Base64 encoded CLK data
      - type: string
      - type: integer

```


#### Addition of an endpoint to retrieve temporary object store credentials

Returns a set of temporary security credentials that the client can use to upload data to the object store.

`/projects/{project_id}/authorise-external-upload`

A valid upload token is required to authorise this call.

The response will contain:

* `credentials`
  * `AccessKeyId` (e.g. `Y4RJU1RNFGK48LGO9I2S`)
  * `SecretAccessKey` (e.g. `sYLRKS1Z7hSjluf6gEbb9066hnx315wHTiACPAjg`)
  * `Expiration` (e.g. `2019-08-08T20:26:12Z`
  * `SessionToken` (e.g. `eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3NLZXkiOiJZNFJKVTFSTkZHSzQ4TEdPOUkyUyIsImF1ZCI6IlBvRWdYUDZ1Vk80NUlzRU5SbmdEWGo1QXU1WWEiLCJhenAiOiJQb0VnWFA2dVZPNDVJc0VOUm5nRFhqNUF1NVlhIiwiZXhwIjoxNTQxODExMDcxLCJpYXQiOjE1NDE4MDc0NzEsImlzcyI6Imh0dHBzOi8vbG9jYWxob3N0Ojk0NDMvb2F1dGgyL3Rva2VuIiwianRpIjoiYTBiMjc2MjktZWUxYS00M2JmLTg3MzktZjMzNzRhNGNkYmMwIn0.ewHqKVFTaP-j_kgZrcOEKroNUjk10GEp8bqQjxBbYVovV0nHO985VnRESFbcT6XMDDKHZiWqN2vi_ETX_u3Q-w`)
* `upload`
  * `endpoint` (e.g. `minio.anonlink.example.com`)
  * `bucket` (e.g. `anonlink-uploads`)
  * `path` (e.g. `2020/05/Z7hSjluf6gEbxxyy`)

This endpoint may fail if the object store does not support creating temporary credentials.
This feature may be entirely disabled in the server configuration, see `settings.py` and `values.yaml`.

The temporary credentials must be configured to have a security policy only allowing uploads to a particular folder in
a bucket for a period of time. The client will not be able to list objects or retrieve objects from this bucket. 

An example policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "s3:PutObject"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:s3:::anonlink-uploads/2020/05/Z7hSjluf6gEbxxyy/*"
      ],
      "Sid": "Upload-access-to-specific-bucket-only"
    }
  ]
}
```


A possible future extension is to take advantage of MinIO's [Security Token Service (STS)](https://docs.min.io/docs/minio-sts-quickstart-guide.html)
to enable clients to request temporary credentials using their existing identity management system.

Relevant links:

* https://github.com/minio/minio/blob/master/docs/sts/assume-role.md
* https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
* https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html#generating-a-presigned-url-to-upload-a-file
* https://docs.min.io/docs/upload-files-from-browser-using-pre-signed-urls.html

*Test/prototype procedure*

Need to create a new user (can't use the root credentials for sts)

```sh
$ docker run -it --entrypoint /bin/sh minio/mc
# mc config host add minio http://192.168.1.25:9000 AKIAIOSFODNN7EXAMPLE wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
# mc admin user add minio newuser newuser123
# mc admin policy set minio writeonly user=newuser
```

Add a _restricted_ section to your `.aws/configure`:

```
[restricted]
aws_access_key_id = newuser
aws_secret_access_key = newuser123
region = us-east-1
```

In another terminal use the aws cli to fetch temp credentials:

```
aws --profile restricted --endpoint-url http://localhost:9000 sts assume-role --policy '{"Version":"2012-10-17","Statement":[{"Sid":"Stmt1","Effect":"Allow","Action":"s3:*","Resource":"arn:aws:s3:::*"}]}' --role-arn arn:xxx:xxx:xxx:xxxx --role-session-name anything
```

Alternatively use minio or boto3


### Client Side Specification 

The client side implementation will be in `anonlink-client`, there will be both a public, documented, Python API as well as
an implementation via the command line tool.

Uploading will be implemented using either [`boto3`](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html) or 
[MinIO](https://docs.min.io/docs/python-client-api-reference) at the implementors discretion.

In the default case, uploading via the client tool will involve making the three network requests in sequence: 

- Retrieving temporary object store credentials.
- Uploading encodings to the object store.
- Informing the anonlink entity service of the upload.


If the user already has object store credentials (e.g. for `S3`) they can upload without having to request
temporary credentials. The anonlink client tool aims to deal with this transparently.

#### Example client tool usage

The default case using temporary credentials for our object store:

```sh
$ anonlink upload mydata.csv <AUTH params etc>
```

Where the user wants our client to upload to their own bucket, optionally providing the AWS credential profile to use:

```sh
$ anonlink upload mydata.csv [--profile easd] --upload-to=s3://my-own-bucket/mydata.csv <AUTH params etc>
```

If the user wants to use already uploaded data, they will have to either explicitly provide the anonlink entity service
with credentials that are appropriate to share with the service, or explicitly request temporary credentials. 

```sh
$ anonlink upload s3://my-own-bucket/mydata.csv [--profile easd] --request-read-only-credentials \
           <AUTH params etc>
```

or 
```sh
$ anonlink upload s3://my-own-bucket/mydata.csv [--profile easd] --share-aws-credentials-with-server \
           <AUTH params etc>
```

It is very important that the client doesn't assume it can share a user's AWS credentials with the service.

This means something like:
```
$ anonlink upload s3://my-own-bucket/mydata.csv
```

Explicitly telling us could be via the additional command line arguments shown above,  or an `~/.anonlink` config file
or via environment variables. 

#### Progress Handling

The Python api to upload encodings to the object store will be written to support a user supplied callback. See example progress 
callbacks for [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html#the-callback-parameter) and
[MinIO](https://github.com/minio/minio-py/blob/master/examples/progress.py). 

The command line interface will use the callback mechanism to display progress using [`tqdm`](https://tqdm.github.io/) - already 
used to show progress during hashing. 

#### Error Handling

Errors during upload detected by the object store client will be caught and raised as an `AnonlinkClientError`. 
`ResponseError` exceptions should be caught and presented to the command line user without a traceback. The object store
credentials may be used during a retry attempt. If the object store credentials have expired the client may automatically
request new credentials from the Anonlink Entity Service.

### Deployment Changes

Extra policy, user, & bucket must be created in MinIO. This can be carried out by a new container
`init_object_store` that includes the `mc` command line tool for Minio. In the kubernetes deployment
this will run as a job similar to our `init_db` job.

An option to expose Minio will be added to the deployment.
When the option is enabled, Minio will be exposed via an ingress. 

#### Ingress configuration

**Domain** By default Minio will be available at the `minio` sub-domain of the service's domain/s. 

**Proxy** The ingress controller may need to be modified to support proxying large uploads through to MinIO.

**TLS** As MinIO is going to be exposed to the internet it must be protected with a certificate.

https://docs.min.io/docs/generate-let-s-encypt-certificate-using-concert-for-minio.html
https://docs.min.io/docs/setup-nginx-proxy-with-minio.html

## Security consideration

The user is supplying an object store address - can we trust it? We don't want to pull the wrong data. Misuse could include
making our server download illegal data, making our server download terabytes and terabytes of data.

If using our own object store we can dictate the bucket and file, but we want to support an external object store too. 

As exposing Minio increases the attack surface an internal security review of MinIO must be conducted. 
Deployment using default or publicly committed credentials must be mitigated.

## Alternatives (WIP)

The primary alternative that we considered was modification to the Anonlink REST api to handle partial uploads.
The Anonlink api and client would be modified to deal with multipart uploads. The reason this design wasn't
pursued is we would have to design and implement everything on both the server and client side - the retrying
mechanisms, integrity checks, dropped connections, proxy handling etc. 

## Additional Considerations (WIP)

Initially we will support pulling from an S3 like object store. How about direct HTTP/both? Is FTP still common?
Do we support pulling data via HTTP (e.g. someone gives the server a Google Drive or dropbox URL we could pull the data).

Monitoring progress during pulling data, resuming pulling data, identifying and dealing with data corruption, service failure.

Should the entity service deploy a separate publicly available object store, or expose the one it uses internally?

Authentication/presigned urls? Presigned URLs are usually used with non object store clients - enabling direct POST/GET
calls. Need to determine if object store clients can use them to take advantage of chunked uploads, integrity checking etc.
See https://github.com/minio/minio/blob/master/docs/sts/assume-role.md and 
https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html#using-presigned-urls-to-perform-other-s3-operations 

Ability to easily copy from one object store to another? MinIO has a sync

Configuration of client tool - `~/.anonlinkcfg`

Notification of an upload by MinIO into Redis or Postgres is possible. We decided it was not worth the extra complexity as the client
will be uploading via our tool so the client is in a good position to reliably inform the server when the upload is complete.
See the [MinIO bucket notification guide](https://docs.min.io/docs/minio-bucket-notification-guide.html).

What if the object changes or is deleted while we are pulling it?

Anything else?