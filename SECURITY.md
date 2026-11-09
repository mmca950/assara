# Security policy

## Supported versions

Assara is in alpha. Only the latest release (and `main`) receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through GitHub:
**Security** tab of the repository, then **Report a vulnerability** (private security advisory).

Include what you found, the steps to reproduce it (with a public-domain text or a tiny generated file, never
copyrighted material), and the impact you expect. You will get an answer within a week; a fix and an
advisory follow once the problem is confirmed.

## Scope

In scope: the `assara` CLI and package, the Docker image, the skills and templates written by `assara init`
(for example a skill that would lead Claude Code to read files it should not, such as `.secrets/`).

Out of scope: vulnerabilities in third-party tools Assara calls (yt-dlp, instaloader, faster-whisper,
PyMuPDF, poppler, ffmpeg) unless Assara uses them unsafely; report those upstream.
