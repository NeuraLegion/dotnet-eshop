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

test('POST /api/catalog/items?api-version=1.0', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: ['business_constraint_bypass', 'csrf', 'html_injection', 'xss'],
      attackParamLocations: [AttackParamLocation.BODY, AttackParamLocation.QUERY],
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
      method: HttpMethod.POST,
      url: `${baseUrl}/api/catalog/items?api-version=1.0`,
      body: {
        id: 0,
        name: 'Contoso Running Shoes',
        description: 'Lightweight everyday running shoes',
        price: 79.99,
        pictureFileName: 'contoso-running-shoes.png',
        catalogTypeId: 1,
        catalogType: null,
        catalogBrandId: 1,
        catalogBrand: null,
        availableStock: 25,
        restockThreshold: 5,
        maxStockThreshold: 100,
        onReorder: false
      },
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json'
      }
    });
});