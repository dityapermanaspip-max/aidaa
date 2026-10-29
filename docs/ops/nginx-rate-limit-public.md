# Rate-limiting the anonymous questionnaire link

The public questionnaire is AIDAA's only unauthenticated write path. The application caps stored
answers atomically (advisory lock + conditional insert), but nothing there limits how often one client
may POST. That belongs at the edge, so a shared link posted in a group chat cannot burn the whole
respondent quota in a few seconds.

Two places accept the traffic:

- the frontend BFF route `/api/aidaa-public/...` (the real entry point used by `/q/[token]`), and
- the backend path `/api/v1/aidaa/public/...`, if it is ever exposed directly.

Rate-limit the BFF path. If the backend is also public, add the same zone there.

```nginx
# http {} block
limit_req_zone $binary_remote_addr zone=aidaa_public_edge:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=aidaa_public_api:10m  rate=20r/m;

# server {} for the Next.js frontend
location /api/aidaa-public/ {
    limit_req zone=aidaa_public_edge burst=5 nodelay;
    limit_req_status 429;
    client_max_body_size 64k;          # a questionnaire answer is a few KB
    proxy_pass http://darkhive_frontend;
    include /etc/nginx/proxy_params;   # must forward X-Forwarded-For / Host
}

# only if the backend is reachable from the internet
location /api/v1/aidaa/public/ {
    limit_req zone=aidaa_public_api burst=10 nodelay;
    limit_req_status 429;
    client_max_body_size 64k;
    proxy_pass http://aidaa_api;
    include /etc/nginx/proxy_params;
}
```

Notes:

- `10r/m` is a starting point: ten requests per minute per IP allows a respondent to open the page,
  read it and submit, while a paste into a large chat group is throttled. Measure the real answer rate
  before tightening.
- Keep the burst small (`burst=5`). A generous burst defeats the limit.
- If another proxy/CDN sits in front, nginx sees that proxy's address; use the real client IP
  (`real_ip_header X-Forwarded-For` + `set_real_ip_from`) or the zone becomes one global bucket.
- This is flood control, not identity: the questionnaire is deliberately anonymous and stores no IP.
  The number of accepted responses and their timing stay the leader's signal (the link can be
  regenerated to kill the old one instantly).
- `limit_req_status 429` is what the public page needs to show; check that the frontend renders a
  friendly "too many attempts" message rather than a generic error.
