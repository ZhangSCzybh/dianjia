# Dianplus Cookie Login Design

## Goal

Provide a repeatable command-line login that reads credentials from `.env`, authenticates against Dianplus DevOps, and writes reusable session cookies without exposing their values in console output.

## Verified Protocol

- Login page: `https://devops.dianplus.cn/views/modules/login/login.html`
- Endpoint: `POST https://devops.dianplus.cn/login`
- Request encoding: `application/x-www-form-urlencoded`
- Request fields: `username`, `password`
- Successful verification: HTTP 200 at `https://devops.dianplus.cn/`
- Session cookies: `JSESSIONID` (Secure, HttpOnly, SameSite=Lax) and `CURRENT_ROLERELATION_ID`

## Design

The project uses only the Python standard library. `login.py` loads a minimal dotenv file, sends a URL-encoded POST through an opener with `CookieJar`, follows redirects, rejects responses that leave the user on the login page, and persists reusable cookie artifacts.

The command creates two Git-ignored artifacts: `session.cookies.txt`, containing a single cookie-header value for direct use in later HTTP clients, and `session.cookies.json`, containing cookie metadata plus the header value for programmatic consumers. Values are never printed.

## Error Handling

Missing environment variables, HTTP errors, connection failures, absent session cookies, and an unchanged login-page destination exit nonzero with a concise diagnostic. Existing output files are written only after a successful authenticated response.

## Testing

`unittest` covers dotenv parsing, URL-encoded form construction, accepted success detection, rejected login-page responses, cookie header formatting, and artifact serialization. Tests use constructed `http.cookiejar.Cookie` values and no live credentials. A separate manual live run validates the endpoint contract.
