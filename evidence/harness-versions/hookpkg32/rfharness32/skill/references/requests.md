# RequestsLibrary: API testing

REQUESTSLIBRARY -- API TESTING

VERIFIED CORE:
- Create Session    api    http://127.0.0.1:8000        (alias + base URL)
- ${resp}=    GET On Session    api    /users.json    expected_status=200
- Status Should Be    200    ${resp}
- ${data}=    Set Variable    ${resp.json()}            (outside Evaluate: ${resp.json()}; inside Evaluate: $resp.json())
- Should Be Equal As Strings    ${resp.json()}[0][name]    Ann
- ${resp}=    POST On Session    api    /items    json=${body}    (json= for JSON bodies, NOT data=)
- ${resp}=    GET On Session    api    /missing    expected_status=404     (non-2xx without failing)
- `grep -i "on session" .rf/docs/RequestsLibrary.md` shows the real parameters (alias, url, data, json, expected_status, msg, **kwargs).

--- requests locator reference ---
tips:
  - SESSION: Create Session with an alias + base URL, then use GET/POST/PUT/PATCH/DELETE On Session with that alias and a RELATIVE path. A bare Get/Post takes a full URL.
  - RESPONSE: On-Session keywords RETURN the response — capture with ${resp}=. Read status via ${resp.status_code}, body via ${resp.json()}, a field via ${resp.json()["bookingid"]}.
  - EVALUATE: Inside Evaluate use the BARE name ($resp, $token); OUTSIDE Evaluate use ${resp.json()}. Do NOT reach for Evaluate to compare status/fields — use the native assertion keywords.
  - STATUS ASSERT: use 'Status Should Be    200    ${resp}' — NOT an Evaluate equality on ${resp.status_code}. This is the biggest Evaluate-call remover.
  - BODY/HEADERS: Send a JSON body with json=<dict> — NOT data=. Set headers with headers=${headers}. A 400/415 usually means data= was used, the body was a string, or Content-Type: application/json is missing.
  - BODY CONSTRUCTION: Build the JSON body dict, do NOT pass a repr-string. Easiest: inline Python eval — json=${{ {"firstname": "Jane", "totalprice": 111, "depositpaid": True, "bookingdates": {"checkin": "2024-01-01"}} }} (a real Python literal, so True/False/None and nested dicts work). Or define it first and pass it: assign ${body}= via Evaluate  {"firstname": "Jane", ...}  THEN reference json=${body} in the POST — never POST before ${body} exists. Avoid Set Variable/Create Dictionary gymnastics for JSON bodies.
  - AUTH TOKEN: capture the token from ${resp.json()["token"]}, then send it as a cookie header: headers=${{"Cookie": "token=" + $token}} (or a &{headers} dict). Required for PUT/DELETE on restful-booker.
  - NON-2XX: pass expected_status=404 (or expected_status=anything) so an error response is RETURNED instead of raising — needed to assert a deleted resource returns 404.
  - NAMED ARGS: RequestsLibrary named args are positional name=value tokens (expected_status=200, json=${body}, headers=${headers}), not RF &{dict} kwargs.
warnings:
  - ${resp.json()} works OUTSIDE Evaluate; inside Evaluate it is $resp.json() (bare) — mixing them is the #1 API time sink.
  - Without expected_status=, a non-2xx response RAISES — you cannot then assert a 404; pass expected_status to capture error responses.
  - PUT/DELETE that return 403/Forbidden usually mean the auth token cookie header was not sent.
examples:
  - Create Session    rb    https://restful-booker.herokuapp.com      # alias + base URL
  - ${resp}=    POST On Session    rb    /booking    json=${{ {"firstname": "Jane", "lastname": "Doe", "totalprice": 111, "depositpaid": True, "bookingdates": {"checkin": "2024-01-01", "checkout": "2024-01-05"}} }}      # build the JSON body inline with ${{ }} — no Set Variable/Create Dictionary
  - ${resp}=    POST On Session    rb    /auth    json=${creds}      # or define ${creds}= first, then reference it (never POST before it exists)
  - Status Should Be    200    ${resp}      # native status assertion (not Evaluate)
  - ${token}=    Set Variable    ${resp.json()["token"]}      # read a JSON field outside Evaluate
  - ${resp}=    GET On Session    rb    /booking/${id}    expected_status=404      # assert a deleted resource → 404 without raising
  - ${resp}=    DELETE On Session    rb    /booking/${id}    headers=${{"Cookie": "token=" + $token}}      # auth token cookie header
