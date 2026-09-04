# Dianplus Quick Login

Use this dependency-free Python script to exchange the credentials in `.env` for Dianplus DevOps session cookies.

```sh
python3 login.py
```

It creates these owner-readable-only files in the current directory:

- `session.cookies.txt`: the cookie value for a subsequent request's `Cookie` header.
- `session.cookies.json`: the same header plus cookie metadata for programmatic consumers.

For example, a later request can use the saved value without putting it on the command line:

```sh
curl -H "Cookie: $(tr -d '\n' < session.cookies.txt)" https://devops.dianplus.cn/
```

Optional arguments:

```sh
python3 login.py --env-file /path/to/.env --output-dir /path/to/session
```

The script succeeds only when it receives a `JSESSIONID` and finishes away from the login endpoint. It never prints passwords or Cookie values by default.

## Extract Trace SQL

Pass the Trace ID as a command-line argument. The script refreshes the session, posts the Trace ID to the DevOps Trace endpoint, skips any trace metadata after `行查询语句` (for example `/*traceId:...*/`), and prints only the SQL beginning at its first SQL keyword in `resultObject[0].children[0].details`.

```sh
python3 trace_sql.py <traceId>
```

The SQL is also saved by default to `trace-sql/<traceId>.sql` with owner-only permissions. To choose a different destination:

```sh
python3 trace_sql.py <traceId> --output trace.sql
```

`DIANPLUS_TRACE_URL` is optional in `.env`; it defaults to the current DevOps Trace endpoint.
