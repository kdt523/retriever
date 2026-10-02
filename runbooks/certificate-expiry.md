---
title: TLS certificate expired or invalid
scope: Clients or services fail TLS handshakes because a certificate has expired, was not renewed by cert-manager, or does not match the hostname.
tools: [openssl s_client, kubectl get certificate, kubectl describe certificate, kubectl get secret, kubectl logs cert-manager]
cautions:
  - Never disable certificate verification in clients as a fix.
  - Deleting a TLS Secret makes the Ingress serve a default self-signed certificate until it is reissued.
related: [ingress-502-503-504, dependency-down]
---

Expiry is entirely predictable, so treat a surprise expiry as a monitoring gap as well as an outage.

## Symptoms

- Browsers show `NET::ERR_CERT_DATE_INVALID`; clients log `x509: certificate has expired or is not yet valid: current time 2026-03-01T10:00:00Z is after 2026-02-28T23:59:59Z`.
- Or `tls: failed to verify certificate: x509: certificate is valid for a.example.com, not b.example.com`.
- Or `SSL: CERTIFICATE_VERIFY_FAILED` in Python clients calling an internal service.
- cert-manager `Certificate` shows `READY False`.

## Checks

1. Check what is being served: `openssl s_client -connect <host>:443 -servername <host> </dev/null | openssl x509 -noout -dates -subject -ext subjectAltName`.
2. Check cert-manager state: `kubectl get certificate -A` and `kubectl describe certificate <name>`; look at the `CertificateRequest` and `Order` events.
3. Read cert-manager logs for ACME errors, for example a failing HTTP-01 challenge.
4. Check the Ingress `tls.secretName` points at the Secret that cert-manager updates.
5. For mTLS between services, check the CA bundle and client certificates too.

## Likely causes

- cert-manager could not complete the ACME challenge (DNS or ingress change, rate limits).
- A manually created certificate that nobody renewed.
- The Ingress references the wrong Secret, or a hostname is missing from the certificate.
- Clock skew on a node (rare; makes valid certificates look not yet valid).

## Fix

- Fix the challenge path, then trigger renewal: `cmctl renew <certificate>` or delete the failed `CertificateRequest` to retry.
- Add the missing hostname to the Certificate's `dnsNames`.
- Point the Ingress `tls.secretName` at the right Secret.
- Add alerting on `certmanager_certificate_expiration_timestamp_seconds` less than 14 days away.

## Rollback / escalation

There is nothing to roll back to once a certificate expires; renewal is the fix. Escalate to the platform or security team immediately for public endpoints.
