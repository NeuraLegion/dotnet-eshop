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

test('GET /api/catalog/items/withsemanticrelevance', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: ['business_constraint_bypass', 'sqli', 'xss', 'csrf', 'secret_tokens'],
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
      url: `${baseUrl}/api/catalog/items/withsemanticrelevance?text=example%20search%20text&PageSize=10&PageIndex=0`
    });
});