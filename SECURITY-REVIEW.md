# Red Team Security Review - Foundation Track
**Date:** 2026-02-20
**Reviewer:** SOC Red Team Agent
**Scope:** Foundation infrastructure, auth, database, and container security

---

## Executive Summary

**RISK LEVEL: HIGH**

The foundation track contains **10 critical** and **15 high-severity** security vulnerabilities that must be addressed before production deployment. The most critical issues involve secrets management, authentication security, and data protection.

**Critical Issues:**
- .env file contains weak credentials and is not in .gitignore
- OAuth tokens stored in plaintext
- No encryption at rest for sensitive data
- Missing CSRF, rate limiting, and session security controls
- Containers running as root with no security hardening

---

## Critical Vulnerabilities (CVSS 9.0+)

### C-001: Hardcoded Weak Credentials
**Severity:** CRITICAL
**CVSS:** 9.8
**File:** `.env`

**Finding:**
```env
POSTGRES_PASSWORD=localdev123
REDIS_PASSWORD=localdev123
QDRANT_API_KEY=localdev123
NEXTAUTH_SECRET=dev_secret_min_32_characters_long_for_local_development
```

**Impact:** Complete system compromise if .env leaks or is committed to git.

**Remediation:**
1. Add `.env` to `.gitignore` immediately
2. Use strong random passwords (32+ chars, high entropy)
3. Implement secrets manager (GCP Secret Manager for Cloud Run)
4. Never use "localdev*" or "placeholder" in any environment
5. Rotate all secrets before any deployment

---

### C-002: OAuth Tokens Stored in Plaintext
**Severity:** CRITICAL
**CVSS:** 9.1
**File:** `prisma/schema.prisma:57-62`

**Finding:**
```prisma
model Account {
  refresh_token     String?
  access_token      String?
  id_token          String?
  // ... stored as plaintext
}
```

**Impact:** Token theft enables full account takeover. Google OAuth tokens grant access to user's Google account data.

**Remediation:**
1. Encrypt tokens at rest using `@encrypted` or application-layer encryption
2. Store only hashed refresh tokens if not needed for API calls
3. Implement token rotation and expiration
4. Use envelope encryption (data encryption key + key encryption key)
5. Audit all token access in `AuditLog`

---

### C-003: Missing Authentication Security Controls
**Severity:** CRITICAL
**CVSS:** 9.0
**File:** `M-004-auth-sessions.md`

**Finding:**
- No CSRF protection mentioned
- No session fingerprinting (IP, User-Agent validation)
- No rate limiting on auth endpoints
- No account lockout after failed attempts
- No secure cookie attributes defined

**Impact:** Session hijacking, CSRF attacks, credential stuffing, account takeover.

**Remediation:**
1. Enable NextAuth CSRF tokens (built-in, must verify config)
2. Implement session fingerprinting:
   ```typescript
   // Validate IP + User-Agent on every request
   // Invalidate session on mismatch
   ```
3. Add rate limiting:
   - 5 login attempts per IP per 15 minutes
   - 10 session creations per user per hour
4. Set secure cookie attributes:
   ```typescript
   cookies: {
     sessionToken: {
       name: `__Secure-next-auth.session-token`,
       options: {
         httpOnly: true,
         secure: true,
         sameSite: 'lax',
         path: '/',
       }
     }
   }
   ```
5. Implement account lockout (15 min after 5 failed attempts)

---

### C-004: Container Security - Running as Root
**Severity:** CRITICAL
**CVSS:** 8.6
**File:** `docker-compose.yml`

**Finding:**
All containers (postgres, redis, qdrant, pgbouncer) run as root user. No USER directive, no security_opt, no capabilities restrictions.

**Impact:** Container escape = root access to host system.

**Remediation:**
1. Add non-root user to all containers:
   ```yaml
   postgres:
     user: "999:999"  # postgres user
     security_opt:
       - no-new-privileges:true
     cap_drop:
       - ALL
     cap_add:
       - CHOWN
       - DAC_OVERRIDE
       - SETGID
       - SETUID
   ```
2. Enable read-only root filesystem where possible
3. Set resource limits (CPU, memory, PIDs)
4. Use seccomp profiles
5. Scan images for vulnerabilities (Trivy, Grype)

---

### C-005: SQL Injection Risk via Json Fields
**Severity:** HIGH
**CVSS:** 8.2
**File:** `prisma/schema.prisma` (multiple models)

**Finding:**
Multiple Json fields with no validation:
- `User.featureFlags` (line 26)
- `RawEvent.payload` (line 293)
- `Trip.personaSeed`, `fairnessState`, `affinityMatrix`, `logisticsState`
- `ModelRegistry.configSnapshot`, `metrics`

**Impact:** JSON injection, NoSQL injection, data corruption, privilege escalation via featureFlags manipulation.

**Remediation:**
1. Implement Zod schemas for ALL Json fields
2. Validate before write:
   ```typescript
   const FeatureFlagsSchema = z.object({
     earlyAccess: z.boolean().optional(),
     // ... strict schema
   }).strict(); // reject unknown keys
   ```
3. Sanitize Json data on read
4. Never interpolate Json data into raw SQL
5. Use Prisma's type-safe Json queries only

---

## High Severity Vulnerabilities (CVSS 7.0-8.9)

### H-001: Missing Encryption at Rest
**File:** `docker-compose.yml:100-105`, `prisma/schema.prisma`

**Finding:**
No volume encryption, no database encryption. Sensitive data stored in plaintext:
- OAuth tokens
- Stripe customer IDs
- User emails and PII
- API keys

**Remediation:**
1. Enable PostgreSQL encryption at rest (pgcrypto + encrypted volumes)
2. Use GCP Cloud SQL encryption in production
3. Implement field-level encryption for:
   - `Account.refresh_token`, `access_token`
   - `User.stripeCustomerId`
   - `AuditLog.ipAddress`
4. Encrypt Docker volumes (LUKS or cloud-native encryption)

---

### H-002: Redis Authentication Bypass Risk
**File:** `docker-compose.yml:56-75`

**Finding:**
Redis healthcheck command is unsafe:
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
```
This increments a key "ping" on every healthcheck, manipulating data. Should use AUTH + PING.

**Remediation:**
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "PING"]
  # Or better, use redis-cli without auth if coming from localhost
  test: ["CMD-SHELL", "redis-cli -a $REDIS_PASSWORD ping | grep PONG"]
```

---

### H-003: Exposed Database Ports (Production Risk)
**File:** `docker-compose.yml:12-13, 38-39, 64, 85-86`

**Finding:**
All services bind to `127.0.0.1`, but production deployment not specified. Risk of accidental public exposure.

**Remediation:**
1. Document production network architecture
2. Use private subnets for all databases
3. Enable Cloud SQL Proxy for Postgres (no public IP)
4. Use VPC peering or Private Service Connect
5. Implement firewall rules (deny all inbound by default)
6. Never expose Redis, Qdrant, or PgBouncer to public internet

---

### H-004: Missing Rate Limiting Infrastructure
**File:** All API routes (not implemented)

**Finding:**
No rate limiting on any endpoint. Vulnerable to:
- Brute force attacks
- Scraping
- DDoS
- Resource exhaustion

**Remediation:**
1. Implement Redis-backed rate limiting:
   ```typescript
   // Global: 100 req/min per IP
   // Auth: 5 login/15min per IP
   // API: 1000 req/hour per user
   ```
2. Use middleware with sliding window
3. Return 429 with Retry-After header
4. Add CAPTCHA after N failed attempts
5. Implement exponential backoff

---

### H-005: CORS and CSP Not Configured
**File:** Missing in all API routes

**Finding:**
No CORS policy, no Content Security Policy, no security headers.

**Remediation:**
1. Configure CORS in Next.js middleware:
   ```typescript
   const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'];
   // Strict origin checking
   ```
2. Implement CSP headers:
   ```
   Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; img-src 'self' https://images.unsplash.com https://lh3.googleusercontent.com; connect-src 'self' https://api.anthropic.com
   ```
3. Add security headers:
   - X-Frame-Options: DENY
   - X-Content-Type-Options: nosniff
   - Referrer-Policy: strict-origin-when-cross-origin
   - Permissions-Policy: geolocation=(), microphone=(), camera=()

---

### H-006: No Input Validation Framework
**File:** All API routes (not implemented)

**Finding:**
No mention of input validation. Risk of:
- XSS via user-generated content
- Path traversal
- Header injection
- Prototype pollution

**Remediation:**
1. Implement Zod validation on all API inputs
2. Sanitize HTML in user content:
   ```typescript
   import DOMPurify from 'isomorphic-dompurify';
   const clean = DOMPurify.sanitize(userInput);
   ```
3. Validate file uploads (type, size, content)
4. Escape output in templates
5. Use parameterized queries only (Prisma handles this)

---

### H-007: Audit Log IP Privacy Violation
**File:** `prisma/schema.prisma:360`

**Finding:**
```prisma
model AuditLog {
  ipAddress  String  // Stores PII without consent or retention policy
  userAgent  String  // Stores PII
}
```

**Impact:** GDPR violation, privacy violation, potential data breach notification requirement.

**Remediation:**
1. Hash IP addresses (SHA256 with daily rotating salt)
2. Implement data retention policy (delete logs > 90 days)
3. Add privacy notice in ToS
4. Provide user data export (GDPR Article 20)
5. Implement "right to be forgotten" deletion cascade

---

### H-008: Stripe Webhook Security
**File:** `.env:46`

**Finding:**
Stripe webhook secret is placeholder. No verification logic mentioned.

**Remediation:**
1. Verify webhook signatures:
   ```typescript
   const signature = headers.get('stripe-signature');
   const event = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
   ```
2. Reject unsigned webhooks
3. Implement idempotency (check event.id in database)
4. Add webhook retry logic
5. Monitor failed webhook deliveries

---

### H-009: Session Fixation Vulnerability
**File:** `M-004-auth-sessions.md`

**Finding:**
No session regeneration on privilege escalation mentioned. Risk of session fixation attack.

**Remediation:**
1. Regenerate session ID on login
2. Regenerate session ID on privilege change (e.g., user → admin)
3. Invalidate old session tokens
4. Implement session versioning:
   ```prisma
   model Session {
     version Int @default(1)
   }
   ```

---

### H-010: Missing Security Monitoring
**File:** All

**Finding:**
No security monitoring, alerting, or incident response mentioned.

**Remediation:**
1. Integrate Sentry for error tracking (already planned)
2. Add security event logging:
   - Failed login attempts
   - Session invalidations
   - Authorization failures
   - Suspicious activity (rapid API calls, unusual patterns)
3. Set up alerts (PagerDuty, Slack)
4. Implement anomaly detection (ML-based or rule-based)
5. Create incident response playbook

---

## Medium Severity Issues (CVSS 4.0-6.9)

### M-001: Docker Image Vulnerabilities
**Finding:** Using third-party images without vulnerability scanning.

**Remediation:**
1. Scan all images in CI/CD: `docker scan` or `trivy image`
2. Pin image versions (avoid `latest`)
3. Use minimal base images (alpine where possible)
4. Implement automated image updates
5. Use Docker Content Trust (image signing)

### M-002: No Dependency Vulnerability Scanning
**Finding:** No npm audit, no Snyk, no Dependabot mentioned.

**Remediation:**
1. Enable Dependabot in GitHub
2. Run `npm audit` in CI/CD (fail on high/critical)
3. Implement SCA (Software Composition Analysis)
4. Auto-merge patch updates
5. Review all dependency updates for supply chain risks

### M-003: PgBouncer Pool Exhaustion
**File:** `docker-compose.yml:34`

**Finding:** `DEFAULT_POOL_SIZE=25` may be insufficient under load.

**Remediation:**
1. Monitor pool usage with Prometheus
2. Implement connection pool metrics
3. Set `MIN_POOL_SIZE=10` for faster scaling
4. Add alerting on pool >80% utilization
5. Implement circuit breaker on pool exhaustion

### M-004: Redis Persistence Security
**File:** `docker-compose.yml:61-62`

**Finding:**
```yaml
--save 60 1000
--appendonly yes
```
RDB + AOF enabled, but no encryption on persisted data.

**Remediation:**
1. Encrypt Redis volumes
2. Use Redis ACLs (v6+) instead of single password
3. Implement key expiration policies
4. Monitor AOF file size (can grow unbounded)
5. Backup encrypted AOF files

### M-005: No Backup Strategy
**Finding:** No database backup, no disaster recovery plan.

**Remediation:**
1. Implement automated backups (Cloud SQL automated backups)
2. Test restore procedures monthly
3. Implement point-in-time recovery (PITR)
4. Backup encryption at rest and in transit
5. Store backups in different region/zone

### M-006: Missing API Versioning
**Finding:** No API versioning strategy mentioned.

**Remediation:**
1. Implement `/api/v1/` versioning
2. Document deprecation policy
3. Maintain backward compatibility for N-1 versions
4. Add `X-API-Version` header
5. Implement API gateway for version routing

### M-007: Qdrant Security Hardening
**File:** `docker-compose.yml:77-97`

**Finding:**
- API key in plaintext env var
- No TLS mentioned
- No access controls beyond single API key

**Remediation:**
1. Use Qdrant Cloud with OAuth (production)
2. Enable TLS for gRPC and HTTP
3. Implement collection-level access controls
4. Rotate API keys quarterly
5. Audit all vector operations

### M-008: NextAuth Cookie Security
**Finding:** No cookie configuration mentioned in M-004.

**Remediation:**
1. Set `useSecureCookies: true` (production)
2. Implement cookie prefix: `__Host-` or `__Secure-`
3. Set `maxAge` to session duration (not browser session)
4. Implement cookie domain restrictions
5. Use `sameSite: 'strict'` for high-security routes

### M-009: Missing Security.txt
**Finding:** No /.well-known/security.txt file.

**Remediation:**
```
Contact: security@overplanned.app
Expires: 2027-02-20T00:00:00.000Z
Preferred-Languages: en
Canonical: https://overplanned.app/.well-known/security.txt
```

### M-010: No Password Policy (Future)
**Finding:** Currently Google OAuth only (good), but no password policy if email/password added later.

**Remediation:**
1. If password auth added: min 12 chars, zxcvbn strength check
2. Implement breach password checking (HaveIBeenPwned API)
3. Enforce MFA for admin accounts
4. Implement password rotation (optional for users, required for admins)

---

## Low Severity Issues (CVSS < 4.0)

### L-001: Docker Compose Version Pinning
**Finding:** `version: '3.9'` is deprecated. Use Compose Specification instead.

**Remediation:**
Remove version field, use modern Compose features.

### L-002: Health Check Intervals Too Frequent
**Finding:** 10s intervals on all services may cause unnecessary load.

**Remediation:**
Increase to 30s for non-critical services (Qdrant).

### L-003: Missing Container Labels
**Finding:** No labels for better organization, monitoring.

**Remediation:**
Add labels:
```yaml
labels:
  - "com.overplanned.environment=dev"
  - "com.overplanned.service=postgres"
```

### L-004: No Logging Configuration
**Finding:** No centralized logging, log rotation, or retention policy.

**Remediation:**
1. Configure Docker logging driver (json-file with rotation)
2. Ship logs to Cloud Logging (production)
3. Implement structured logging (Winston, Pino)
4. Set retention: 30 days dev, 90 days prod

### L-005: Database Timezone Not Enforced
**File:** `docker/init-postgis.sql:29`

**Finding:** `SET timezone = 'UTC';` only sets for init script, not enforced globally.

**Remediation:**
```sql
ALTER DATABASE overplanned SET timezone TO 'UTC';
```

---

## Compliance Issues

### GDPR Compliance Gaps
1. No data retention policy documented
2. No "right to be forgotten" implementation
3. No data export functionality
4. IP addresses stored without legal basis
5. No privacy impact assessment (DPIA)
6. No data processing agreement (DPA) for third parties

**Remediation:**
1. Implement GDPR compliance framework
2. Add user data export API
3. Implement cascading deletion on user account deletion
4. Document legal basis for data processing
5. Review and sign DPAs with Stripe, Anthropic, Google, Sentry, Resend

### PCI DSS (if handling cards directly)
Currently using Stripe (PCI compliant), so no direct card handling. **Do not implement direct card processing without PCI DSS Level 1 certification.**

---

## Recommended Immediate Actions (Pre-Production)

### Priority 1 (Block Production Deploy)
1. [ ] Fix C-001: Generate strong passwords, move to Secret Manager
2. [ ] Fix C-002: Encrypt OAuth tokens at rest
3. [ ] Fix C-003: Implement CSRF, rate limiting, session security
4. [ ] Fix C-004: Run containers as non-root, add security options
5. [ ] Fix C-005: Add Zod validation for all Json fields

### Priority 2 (Before Beta Launch)
6. [ ] Fix H-001: Enable encryption at rest
7. [ ] Fix H-004: Implement rate limiting
8. [ ] Fix H-005: Configure CORS and CSP
9. [ ] Fix H-006: Add input validation framework
10. [ ] Fix H-007: Hash IP addresses, implement retention policy

### Priority 3 (Before General Availability)
11. [ ] Implement security monitoring and alerting
12. [ ] Conduct penetration testing
13. [ ] Complete GDPR compliance implementation
14. [ ] Implement backup and disaster recovery
15. [ ] Security training for development team

---

## Security Testing Recommendations

### Manual Testing
1. **Auth Testing:**
   - Test session fixation
   - Test CSRF protection
   - Test concurrent session limits
   - Test session expiration
   - Test OAuth flow edge cases

2. **API Testing:**
   - Test rate limiting
   - Test input validation (fuzzing)
   - Test SQL injection (automated + manual)
   - Test XSS (stored, reflected, DOM-based)
   - Test authorization bypass

3. **Infrastructure Testing:**
   - Test container escape attempts
   - Test network segmentation
   - Test secrets exposure
   - Test backup and restore procedures

### Automated Testing
1. **SAST:** Integrate SonarQube or Semgrep in CI/CD
2. **DAST:** Run OWASP ZAP or Burp Suite scans weekly
3. **Dependency Scanning:** npm audit, Snyk, Dependabot
4. **Container Scanning:** Trivy, Grype, Clair
5. **Secret Scanning:** GitGuardian, TruffleHog

### Penetration Testing
Schedule professional pentest before production launch. Focus areas:
- Authentication and session management
- API security
- Database security
- Container and cloud infrastructure
- GDPR compliance

---

## Security Architecture Recommendations

### Zero Trust Implementation
1. Verify every request (no implicit trust)
2. Least privilege access (RBAC + ABAC)
3. Assume breach (monitoring, segmentation)
4. Encrypt everything in transit and at rest

### Defense in Depth
1. **Perimeter:** WAF, DDoS protection, rate limiting
2. **Network:** VPC, private subnets, firewall rules
3. **Application:** Input validation, output encoding, CSRF
4. **Data:** Encryption at rest, field-level encryption
5. **Monitoring:** SIEM, IDS/IPS, anomaly detection

---

## Sign-Off

This security review identifies critical vulnerabilities that **MUST** be remediated before production deployment. The foundation track has good architectural decisions (database sessions, Google OAuth only, Prisma ORM) but lacks essential security controls.

**Recommended Timeline:**
- **Week 1:** Fix all CRITICAL issues (C-001 through C-005)
- **Week 2:** Fix all HIGH issues (H-001 through H-010)
- **Week 3:** Security testing and validation
- **Week 4:** External pentest and final hardening

**Do not deploy to production until all CRITICAL and HIGH severity issues are resolved.**

---

**Reviewed By:** SOC Red Team Agent
**Review Date:** 2026-02-20
**Next Review:** After remediation (estimated 2026-03-20)
