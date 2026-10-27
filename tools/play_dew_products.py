#!/usr/bin/env python3
"""Create or update an app's Google Play Dew packs (dew_100 … dew_5000).

Entity's Google Play edition sells these packs (src/dew_play.zi). Play
prices are the node's Dew price (from its XMR rate) plus 10%, converted to
every Play region with Google's rates and taxes, and rounded up to a clean
amount in each local currency. The app needs an uploaded Google Play edition
bundle first. The service account key is read, never printed.

    tools/play_dew_products.py KEY.json PACKAGE [--apply]
"""
import base64
import json
import math
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

API = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/'
PACKS = (100, 500, 1000, 5000)
MARKUP = Decimal('1.10')
REFERENCE = Decimal(1000)


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def access_token(key_path):
    account = json.loads(Path(key_path).read_text())
    now = int(time.time())
    claims = {'iss': account['client_email'], 'scope': 'https://www.googleapis.com/auth/androidpublisher',
              'aud': 'https://oauth2.googleapis.com/token', 'iat': now, 'exp': now + 3600}
    unsigned = b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode()) + '.' + b64url(json.dumps(claims).encode())
    with tempfile.NamedTemporaryFile('w', suffix='.pem') as key:
        key.write(account['private_key'])
        key.flush()
        signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', key.name], input=unsigned.encode(),
                                   capture_output=True, check=True).stdout
    body = urllib.parse.urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                   'assertion': unsigned + '.' + b64url(signature)}).encode()
    with urllib.request.urlopen('https://oauth2.googleapis.com/token', body, timeout=60) as response:
        return json.load(response)['access_token']


class Play:
    def __init__(self, key_path, package):
        self.token = access_token(key_path)
        self.package = package

    def call(self, method, path, body=None):
        request = urllib.request.Request(API + self.package + path, method=method,
                                         data=None if body is None else json.dumps(body).encode())
        request.add_header('Authorization', 'Bearer ' + self.token)
        request.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode('utf-8', 'replace')


def rates():
    request = urllib.request.Request('https://api.waozi.xyz/api/v1/rates', headers={'User-Agent': 'entity-play-dew-products/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    dew_per_xmr = (Decimal(data['token_units']) / Decimal(10 ** 6)) / (Decimal(data['xmr_atomic_units']) / Decimal(10 ** 12))
    return Decimal(data['xmr_usd_cents']) / 100 / dew_per_xmr, data


def money(price):
    return Decimal(price.get('units', '0') or '0') + Decimal(price.get('nanos', 0) or 0) / Decimal(10 ** 9)


def clean(amount):
    """Round up to two significant digits, in half steps when the first digit is 1."""
    if amount <= 0:
        return amount
    step = Decimal(10) ** (math.floor(math.log10(float(amount))) - 1)
    if amount / step < 20:
        step = step / 2
    return (amount / step).to_integral_value(rounding=ROUND_CEILING) * step


def as_price(currency, amount):
    units = int(amount)
    nanos = int(((amount - units) * Decimal(10 ** 9)).to_integral_value())
    price = {'currencyCode': currency, 'units': str(units)}
    if nanos:
        price['nanos'] = nanos
    return price


def exchange(play):
    """Each region's price for US$1 (exchange rate and included tax), from a large conversion."""
    status, converted = play.call('POST', '/pricing:convertRegionPrices', {'price': as_price('USD', REFERENCE)})
    assert status == 200, converted
    regions = {code: (region['price']['currencyCode'], money(region['price']) / REFERENCE)
               for code, region in converted['convertedRegionPrices'].items()}
    other = converted.get('convertedOtherRegionsPrice', {})
    return regions, other, converted.get('regionVersion', {}).get('version', '2022/02')


def product(package, dew, usd_per_dew, rates_by_region):
    regions_rate, other, version = rates_by_region
    play_usd = Decimal(dew) * usd_per_dew * MARKUP
    regions = []
    for code, (currency, rate) in sorted(regions_rate.items()):
        regions.append({'regionCode': code, 'availability': 'AVAILABLE',
                        'price': as_price(currency, clean(play_usd * rate))})
    option = {'purchaseOptionId': 'buy', 'buyOption': {'legacyCompatible': True, 'multiQuantityEnabled': False},
              'regionalPricingAndAvailabilityConfigs': regions}
    if other.get('usdPrice') and other.get('eurPrice'):
        option['newRegionsConfig'] = {'availability': 'AVAILABLE',
                                      'usdPrice': as_price('USD', clean(play_usd * money(other['usdPrice']) / REFERENCE)),
                                      'eurPrice': as_price('EUR', clean(play_usd * money(other['eurPrice']) / REFERENCE))}
    body = {'packageName': package, 'productId': f'dew_{dew}',
            'listings': [{'languageCode': 'en-US', 'title': f'{dew} Dew',
                          'description': f'{dew} Dew for your Waozi account: the same Dew in every Waozi app and game.'}],
            'purchaseOptions': [option]}
    return body, play_usd.quantize(Decimal('0.01'), rounding=ROUND_CEILING), version


def main():
    key_path, package = sys.argv[1], sys.argv[2]
    apply = '--apply' in sys.argv
    play = Play(key_path, package)
    usd_per_dew, data = rates()
    rates_by_region = exchange(play)
    print(f'node rate: 1 XMR = ${data["xmr_usd_cents"] / 100:.2f}; 1 Dew = ${usd_per_dew:.5f}; Play = +10%, rounded up')
    for dew in PACKS:
        body, play_usd, version = product(package, dew, usd_per_dew, rates_by_region)
        sample = {r['regionCode']: r['price'] for r in body['purchaseOptions'][0]['regionalPricingAndAvailabilityConfigs']
                  if r['regionCode'] in ('US', 'DE', 'GB', 'JP', 'IN', 'BR', 'PY', 'AR')}
        print(f'dew_{dew}: base ${Decimal(dew) * usd_per_dew:.2f} → Play ${play_usd}; '
              f'{len(body["purchaseOptions"][0]["regionalPricingAndAvailabilityConfigs"])} regions; sample {json.dumps(sample)}')
        if not apply:
            continue
        status, answer = play.call('PATCH', f'/onetimeproducts/dew_{dew}?allowMissing=true&updateMask=listings,purchaseOptions&regionsVersion.version={version}', body)
        print('  save', status, answer if status != 200 else 'ok')
        if status != 200:
            continue
        status, answer = play.call('POST', f'/oneTimeProducts/dew_{dew}/purchaseOptions:batchUpdateStates',
                                   {'requests': [{'activatePurchaseOptionRequest': {
                                       'packageName': package, 'productId': f'dew_{dew}', 'purchaseOptionId': 'buy'}}]})
        print('  activate', status, answer if status != 200 else 'ok')


if __name__ == '__main__':
    main()
