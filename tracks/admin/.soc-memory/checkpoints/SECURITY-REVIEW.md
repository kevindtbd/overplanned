# Admin Track - Red Team Security Review

**Review Date:** 2026-02-20
**Scope:** Admin track authentication, authorization, audit logging, and API security
**Severity Levels:** CRITICAL | HIGH | MEDIUM | LOW

---

## Executive Summary

**CRITICAL VULNERABILITIES FOUND: 2**
**HIGH VULNERABILITIES FOUND: 4**
**MEDIUM VULNERABILITIES FOUND: 5**

**Recommendation:** DO NOT DEPLOY to production until critical vulnerabilities are resolved.

The admin track implements comprehensive audit logging and reasonable business logic, but contains **two critical authentication bypass vulnerabilities** that would allow any attacker to gain full admin access. Additionally, multiple high-severity issues around IP spoofing, token exposure, and missing security controls create significant attack surface.

---

## CRITICAL Vulnerabilities

### C-001: Complete Authentication Bypass in FastAPI Admin Endpoints

**File:** `services/api/routers/admin_users.py` (lines 64-76)
**Also affects:** `admin_nodes.py`, all other admin routers

**Issue:**
The admin authentication dependency trusts client-provided HTTP headers without any validation:

```python
async def require_admin_user(request: Request):
    actor_id = request.headers.get("X-Admin-User-Id")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    role = request.headers.get("X-Admin-Role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return actor_id
```

**Attack:**
```bash
curl -H "X-Admin-User-Id: attacker" \
     -H "X-Admin-Role: admin" \
     https://api.overplanned.com/admin/users
```

An attacker can set arbitrary headers to impersonate any admin user and gain full access to all admin endpoints including:
- User data access and modification
- Subscription tier changes (free → lifetime)
- Feature flag overrides
- Node approval/archival
- Model promotion to production
- Token revocation
- Injection queue review

**Impact:**
- Complete compromise of admin panel
- Data exfiltration of all user data
- Privilege escalation of any user account
- Malicious model promotion
- Audit log poisoning with fake actor IDs

**Remediation:**
Replace header-based auth with proper session/JWT validation:

```python
from fastapi import Depends, HTTPException
from app.auth import verify_jwt_token, get_current_user

async def require_admin_user(
    token: str = Depends(oauth2_scheme),
    db: Prisma = Depends(get_db)
):
    payload = verify_jwt_token(token)
    user = await db.user.find_unique(where={"id": payload["sub"]})

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.systemRole != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"id": user.id, "email": user.email}
```

Or use the existing NextAuth session via a shared session store (Redis).

---

### C-002: Type Cast Authentication Bypass in TypeScript Middleware

**File:** `apps/web/middleware/admin.ts` (lines 19-22)

**Issue:**
The TypeScript admin check uses unsafe type casting:

```typescript
const systemRole = (session.user as any).systemRole;

if (systemRole !== 'admin') {
  return NextResponse.json(...)
}
```

**Attack Vector:**
If the session object is compromised or if there's a type confusion vulnerability in NextAuth, an attacker could inject a `systemRole` field. The `as any` cast bypasses TypeScript's type safety.

**Impact:**
- Potential bypass if session structure is manipulated
- No compile-time guarantee that `systemRole` exists
- Runtime errors could expose sensitive data

**Remediation:**
```typescript
import { User } from '@prisma/client';

// Define extended session type
interface AdminUser extends User {
  systemRole: 'admin' | 'user';
}

export async function adminMiddleware(req: NextRequest) {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
    return NextResponse.json(
      { error: 'Unauthorized' },
      { status: 401 }
    );
  }

  // Type-safe check with proper validation
  const user = session.user as User;
  if (!user.systemRole || user.systemRole !== 'admin') {
    return NextResponse.json(
      { error: 'Forbidden' },
      { status: 403 }
    );
  }

  return NextResponse.next();
}
```

Additionally, ensure `systemRole` is explicitly included in the NextAuth session callback.

---

## HIGH Vulnerabilities

### H-001: IP Address Spoofing in Audit Logs

**File:** `services/api/middleware/audit.py` (lines 121-124)

**Issue:**
```python
ip_address = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
if not ip_address:
    ip_address = request.client.host if request.client else "unknown"
```

The `X-Forwarded-For` header is trusted without validation. An attacker can spoof their IP address in audit logs.

**Attack:**
```bash
curl -H "X-Forwarded-For: 127.0.0.1" \
     -H "X-Admin-User-Id: admin123" \
     -H "X-Admin-Role: admin" \
     https://api.overplanned.com/admin/users/victim/subscription-tier \
     -X PATCH -d '{"tier": "free"}'
```

The audit log will show IP `127.0.0.1` instead of the attacker's real IP.

**Impact:**
- Audit trail poisoning
- Inability to trace malicious actions
- Compliance violations (SOC2, GDPR)

**Remediation:**
Trust only the last proxy in a validated chain:

```python
def extract_client_info(request, trusted_proxies: list[str] = None) -> tuple[str, str]:
    """
    Extract IP from X-Forwarded-For, validating proxy chain.
    trusted_proxies should be load balancer IPs in production.
    """
    xff = request.headers.get("X-Forwarded-For", "")

    if xff and trusted_proxies:
        ips = [ip.strip() for ip in xff.split(",")]
        # Take the rightmost IP that's not a trusted proxy
        for ip in reversed(ips):
            if ip not in trusted_proxies:
                ip_address = ip
                break
        else:
            ip_address = request.client.host
    else:
        # In dev/test, fall back to client IP
        ip_address = request.client.host if request.client else "unknown"

    user_agent = request.headers.get("User-Agent", "unknown")
    return ip_address, user_agent
```

---

### H-002: Token Prefix Exposure in Admin UI

**File:** `services/api/routers/admin_safety.py` (line 143, 249)

**Issue:**
```python
token=t.token[:8] + "...",  # Truncate for display
```

Exposing the first 8 characters of tokens reduces entropy and enables pattern matching attacks.

**Attack Scenario:**
If tokens are generated with predictable prefixes (e.g., timestamps, sequential IDs), an attacker with access to the admin panel could:
1. Collect exposed prefixes
2. Infer token generation pattern
3. Brute force remaining characters
4. Gain unauthorized access to shared/invite links

**Impact:**
- Reduced token security
- Potential unauthorized trip access
- Privacy violations

**Remediation:**
```python
# Option 1: Don't show token at all
token="<redacted>",
token_id=t.id,  # Show ID instead for lookup

# Option 2: Show last 4 chars only (like credit cards)
token=f"...{t.token[-4:]}",

# Option 3: Hash display
import hashlib
token_display = hashlib.sha256(t.token.encode()).hexdigest()[:8]
```

---

### H-003: Missing Rate Limiting on Admin Endpoints

**Files:** All admin routers

**Issue:**
None of the admin endpoints implement rate limiting, making them vulnerable to:
- Brute force attacks on any remaining auth
- DoS attacks
- Audit log flooding
- Database resource exhaustion

**Attack:**
```bash
# Flood audit logs
for i in {1..10000}; do
  curl -H "X-Admin-User-Id: admin" -H "X-Admin-Role: admin" \
       https://api.overplanned.com/admin/users &
done
```

**Impact:**
- Service degradation
- Audit log noise (obscuring real malicious activity)
- Database performance issues
- Potential DoS

**Remediation:**
Implement rate limiting middleware:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

@router.get("/admin/users")
@limiter.limit("60/minute")  # 60 requests per minute per IP
async def search_users(...):
    ...

# For write operations, stricter limits
@router.patch("/admin/users/{user_id}/subscription-tier")
@limiter.limit("10/minute")
async def update_subscription_tier(...):
    ...
```

---

### H-004: No CSRF Protection on State-Changing Operations

**Files:** All admin POST/PATCH/DELETE endpoints

**Issue:**
The FastAPI admin endpoints don't implement CSRF tokens for state-changing operations.

**Attack:**
An attacker tricks an admin into visiting a malicious page:

```html
<img src="https://api.overplanned.com/admin/users/victim123/subscription-tier?tier=free" />

<!-- Or with JavaScript -->
<script>
fetch('https://api.overplanned.com/admin/models/model123/promote', {
  method: 'POST',
  credentials: 'include',  // Send session cookie
  body: JSON.stringify({target_stage: 'production'})
});
</script>
```

If the admin is logged in, their session is used to execute the malicious action.

**Impact:**
- Unauthorized user tier changes
- Malicious model promotions
- Data modification/deletion
- Token revocations

**Remediation:**
Implement CSRF protection:

```python
from fastapi_csrf_protect import CsrfProtect

@router.post("/admin/models/{model_id}/promote")
async def promote_model(
    model_id: str,
    body: PromoteRequest,
    csrf_protect: CsrfProtect = Depends(),
    ...
):
    await csrf_protect.validate_csrf(request)
    ...
```

Or use the `SameSite=Strict` cookie attribute to prevent CSRF entirely.

---

## MEDIUM Vulnerabilities

### M-001: Audit Log Tampering (No Integrity Protection)

**File:** `services/api/middleware/audit.py`

**Issue:**
Audit logs are stored in the same Prisma database with no signing, hashing, or append-only guarantees at the database level. An attacker with database access (or SQL injection) could modify or delete logs.

**Remediation:**
- Use database-level append-only tables (PostgreSQL `INSERT`-only permissions)
- Implement cryptographic signing of each log entry
- Store logs in immutable external system (AWS CloudWatch, Datadog)
- Add Merkle tree for tamper detection

```python
import hmac
import hashlib

def sign_audit_entry(entry: dict, secret: str) -> str:
    """Sign audit entry with HMAC-SHA256."""
    message = json.dumps(entry, sort_keys=True)
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

# Store signature in DB
entry_data = {...}
signature = sign_audit_entry(entry_data, settings.AUDIT_SECRET)
await db.auditlog.create(data={**entry_data, "signature": signature})
```

---

### M-002: Model Promotion Cooldown Bypass

**File:** `services/api/routers/admin_models.py` (lines 268-282)

**Issue:**
The promotion cooldown checks `modelName` but not `modelVersion`. An attacker could create multiple versions and promote them in rapid succession.

**Attack:**
```bash
# Create v1.0.1
POST /admin/models/model1/promote {"target_stage": "production"}

# Immediately create v1.0.2 and promote (bypasses cooldown)
POST /admin/models/model2/promote {"target_stage": "production"}
```

**Remediation:**
```python
# Check cooldown per target stage, not per model name
recent_promotion = await db.modelregistry.find_first(
    where={
        "stage": body.target_stage,  # Any model promoted to this stage
        "promotedAt": {
            "gte": datetime.now(timezone.utc) - PROMOTION_COOLDOWN,
        },
    },
    order={"promotedAt": "desc"},
)
```

---

### M-003: Missing Input Validation

**Files:** Multiple admin routers

**Issues:**
- No max length on user-provided strings (e.g., `flagReason`, `alias`)
- No regex validation on email, URLs
- No sanitization of HTML/script content in descriptions
- No validation of JSON payloads in `featureFlags`

**Examples:**
```python
# admin_nodes.py - no max length
class NodeUpdate(BaseModel):
    flagReason: Optional[str] = None  # Could be megabytes of data

# admin_users.py - no validation on feature flags
class FeatureFlagUpdate(BaseModel):
    flags: dict[str, bool]  # Could contain millions of keys
```

**Remediation:**
```python
from pydantic import Field, validator, constr

class NodeUpdate(BaseModel):
    flagReason: Optional[constr(max_length=1000)] = None

class FeatureFlagUpdate(BaseModel):
    flags: dict[constr(max_length=100), bool] = Field(
        ...,
        max_items=50,  # Limit number of flags
    )

    @validator('flags')
    def validate_flag_names(cls, v):
        allowed_flags = {'beta_features', 'early_access', 'debug_mode'}
        for key in v.keys():
            if key not in allowed_flags:
                raise ValueError(f'Invalid flag name: {key}')
        return v
```

---

### M-004: Session Fixation Risk

**File:** `apps/web/middleware/admin.ts`

**Issue:**
No session regeneration after privilege escalation. If a user is promoted from `user` to `admin` role, their existing session is reused.

**Attack:**
1. Attacker obtains user's session ID
2. User is promoted to admin
3. Attacker's stolen session now has admin privileges

**Remediation:**
Force session regeneration when `systemRole` changes:

```typescript
// In the user promotion endpoint
await db.user.update({
  where: { id: userId },
  data: { systemRole: 'admin' }
});

// Invalidate all existing sessions for this user
await db.session.deleteMany({
  where: { userId }
});

// Force re-login
```

---

### M-005: Injection Queue XSS Risk

**File:** `services/api/routers/admin_safety.py` (line 348)

**Issue:**
The injection queue endpoint returns raw user input from `payload` without sanitization:

```python
payload = e.payload if isinstance(e.payload, dict) else {}
rows.append(FlaggedInputRow(
    ...
    payload=payload,  # Raw user input
    ...
))
```

If the admin UI renders this payload without escaping, it's vulnerable to stored XSS.

**Remediation:**
1. **Backend:** Sanitize payload before returning:
```python
import bleach

sanitized_payload = {
    k: bleach.clean(str(v)) if isinstance(v, str) else v
    for k, v in payload.items()
}
```

2. **Frontend:** Ensure React escapes payload rendering or use `dangerouslySetInnerHTML` carefully

---

## LOW Vulnerabilities

### L-001: Verbose Error Messages

**Files:** Multiple

**Issue:**
Error messages leak implementation details:
- `"Wire Prisma via app lifespan"` (reveals framework)
- `"Invalid tier: {tier}. Must be one of: ..."` (reveals internal tier list)

**Remediation:**
Use generic messages in production:
```python
if not user:
    if settings.DEBUG:
        raise HTTPException(status_code=404, detail="User not found")
    else:
        raise HTTPException(status_code=404, detail="Resource not found")
```

---

### L-002: No Request ID Tracking

**Issue:**
Audit logs don't include request IDs for correlating events across microservices.

**Remediation:**
Add request ID middleware and include in audit logs.

---

### L-003: Placeholder Dependencies in Production Code

**Files:** All admin routers

**Issue:**
```python
def _get_db() -> Prisma:
    """Placeholder dependency — wired by app startup."""
    raise NotImplementedError("Wire Prisma via app lifespan")
```

These placeholders will crash in production if not properly wired.

**Remediation:**
- Remove placeholders before deployment
- Add integration tests to verify dependencies are wired
- Use dependency injection framework properly

---

## Recommendations

### Immediate Actions (Before Deployment)
1. **FIX C-001:** Replace header-based auth with JWT/session validation
2. **FIX C-002:** Remove `as any` cast, add proper type guards
3. **FIX H-001:** Validate X-Forwarded-For against trusted proxies
4. **ADD:** Rate limiting on all admin endpoints
5. **ADD:** CSRF protection on state-changing operations

### Short-term (Within Sprint)
1. Implement audit log signing/immutability
2. Add comprehensive input validation
3. Review token generation for predictability
4. Add session fixation protection
5. Sanitize all user input in admin UI

### Long-term
1. Regular penetration testing of admin panel
2. Implement Web Application Firewall (WAF)
3. Add intrusion detection system (IDS) for audit logs
4. Implement admin action MFA for sensitive operations
5. Set up security monitoring and alerting

---

## Security Testing Checklist

Before deploying admin track:

- [ ] Verify FastAPI auth dependencies are properly wired (not placeholders)
- [ ] Test authentication bypass attempts with forged headers
- [ ] Test CSRF attacks on all POST/PATCH/DELETE endpoints
- [ ] Test rate limiting under load
- [ ] Verify audit logs cannot be tampered with
- [ ] Test IP spoofing detection
- [ ] Review all user input sanitization
- [ ] Verify token generation randomness
- [ ] Test session fixation scenarios
- [ ] Run automated security scanner (OWASP ZAP, Burp Suite)
- [ ] Conduct manual penetration test

---

## Conclusion

The admin track demonstrates good security awareness with comprehensive audit logging and business logic validation. However, **the header-based authentication is a critical flaw that must be fixed before any deployment**. Once authentication is properly implemented, the remaining issues are addressable with standard security hardening practices.

**Risk Level:** CRITICAL
**Deployment Recommendation:** BLOCK until C-001 and C-002 are resolved

---

**Reviewed by:** soc-core-lite (Red Team)
**Date:** 2026-02-20
**Track:** Admin (Track 3)
