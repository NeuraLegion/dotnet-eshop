import { test, before, after } from 'node:test';
import { SecRunner } from '@sectester/runner';
import { AttackParamLocation, HttpMethod } from '@sectester/scan';

const timeout = 40 * 60 * 1000;
const baseUrl = process.env.BRIGHT_TARGET_URL!;

let runner!: SecRunner;

before(async () => {
  runner = new SecRunner({
    hostname: process.env.BRIGHT_HOSTNAME!,
    projectId: process.env.BRIGHT_PROJECT_ID!
  });

  await runner.init();
});

after(() => runner.clear());

test('GET /api/catalog/items', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: ['sqli', 'business_constraint_bypass', 'xss', 'id_enumeration'],
      attackParamLocations: [AttackParamLocation.QUERY],
      starMetadata: {
        code_source: "NeuraLegion/dotnet-eshop:main",
        databases: ["PostgreSQL"]
      }
    })
    .setFailFast(false)
    .timeout(timeout)
    .run({
      method: HttpMethod.GET,
      url: `${baseUrl}/api/catalog/items?PageSize=10&PageIndex=0&name=exampleName&type=1&brand=1`
    });
});