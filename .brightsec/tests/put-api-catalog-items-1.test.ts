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

test('PUT /api/catalog/items/1?api-version=2.0', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: [
        'bopla',
        'id_enumeration',
        'business_constraint_bypass',
        'sqli',
        'xss',
        'html_injection',
        'http_method_fuzzing',
        'csrf'
      ],
      attackParamLocations: [
        AttackParamLocation.PATH,
        AttackParamLocation.QUERY,
        AttackParamLocation.BODY
      ],
      starMetadata: {
        code_source: 'NeuraLegion/dotnet-eshop:main',
        databases: ['PostgreSQL', 'Redis'],
        user_roles: []
      },
      poolSize: +process.env.SECTESTER_SCAN_POOL_SIZE || undefined
    })
    .setFailFast(false)
    .timeout(timeout)
    .run({
      method: HttpMethod.PUT,
      url: `${baseUrl}/api/catalog/items/1?api-version=2.0`,
      body: {
        id: 1,
        name: '.NET Bot Black Hoodie',
        description: 'Black hoodie with .NET Bot branding',
        price: 29.99,
        pictureFileName: '1.png',
        catalogTypeId: 1,
        catalogBrandId: 1,
        availableStock: 100,
        restockThreshold: 10,
        maxStockThreshold: 200,
        onReorder: false
      },
      headers: { 'Content-Type': 'application/json' }
    });
});