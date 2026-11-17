import { readFileSync } from 'node:fs';

// This advisory has no patched npm release. Angular uses it only during
// trusted builds with repository-owned glob patterns. Reassess by this date.
const reviewed = new Map([
  ['https://github.com/advisories/GHSA-fc5q-39xc-vjpf', { package: 'picomatch', expires: '2026-12-18' }],
]);

const report = JSON.parse(readFileSync(0, 'utf8'));
if (report.error || report.auditReportVersion !== 2 || !report.vulnerabilities || !report.metadata?.vulnerabilities) {
  throw new Error('Expected a complete npm audit report.');
}

let blocked = false;
let highRoots = 0;
for (const [name, item] of Object.entries(report.vulnerabilities)) {
  for (const entry of item.via) {
    if (typeof entry === 'string' || !['high', 'critical'].includes(entry.severity)) continue;
    highRoots++;
    const exception = reviewed.get(entry.url);
    const expires = exception && new Date(`${exception.expires}T00:00:00Z`);
    if (entry.severity === 'high' && name === exception?.package && Date.now() < expires && item.fixAvailable !== true) {
      console.warn(`Reviewed development advisory: ${entry.url}, review before ${exception.expires}`);
    } else {
      blocked = true;
      console.error(`Unresolved ${entry.severity} advisory in ${name}: ${entry.url}`);
    }
  }
}
if (!highRoots && (report.metadata.vulnerabilities.high || report.metadata.vulnerabilities.critical)) {
  throw new Error('Audit reports high/critical findings without identifying their advisories.');
}
if (blocked) process.exitCode = 1;
