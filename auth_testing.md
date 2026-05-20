# Auth-Gated App Testing Playbook (Nexus AI)

## Step 1: Create Test User & Session via mongosh
```bash
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Backend API test
```bash
curl -X GET "$BACKEND/api/auth/me" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
curl -X GET "$BACKEND/api/dashboard/metrics" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
curl -X GET "$BACKEND/api/pipeline/deals" -H "Authorization: Bearer YOUR_SESSION_TOKEN"
```

## Step 3: Browser cookie injection (Playwright)
```python
await page.context.add_cookies([{
    "name": "session_token",
    "value": "YOUR_SESSION_TOKEN",
    "domain": "nexus-beta-onboard.preview.emergentagent.com",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto("https://nexus-beta-onboard.preview.emergentagent.com/app/dashboard")
```

## Success Indicators
- `/api/auth/me` returns user JSON (200)
- Protected `/api/*` endpoints return scoped data for the user only
- Unauth requests to `/app/*` redirect to `/login`
- `/api/payments/checkout/session` works for both pricing packages

## Cleanup
```bash
mongosh --eval "
use('test_database');
db.users.deleteMany({email: /test\.user\./});
db.user_sessions.deleteMany({session_token: /test_session/});
db.profiles.deleteMany({user_id: /test-user-/});
db.targets.deleteMany({user_id: /test-user-/});
db.deals.deleteMany({user_id: /test-user-/});
db.signals.deleteMany({user_id: /test-user-/});
db.activities.deleteMany({user_id: /test-user-/});
db.payment_transactions.deleteMany({user_id: /test-user-/});
"
```
