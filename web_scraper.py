import requests
from bs4 import BeautifulSoup
import time
import json
import csv
import os
import re
import argparse
from urllib.parse import urlparse, urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

def validate_url(url):
    """URL'nin geçerliliğini kontrol eden fonksiyon
    
    Args:
        url (str): Kontrol edilecek URL
    Returns:
        bool: URL geçerli ise True, değilse False
    """
    url_pattern = re.compile(
        r'^https?://'  # http:// veya https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...veya ip
        r'(?::\d+)?'  # opsiyonel port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    try:
        result = bool(url_pattern.match(url))
        if result:
            parsed = urlparse(url)
            return all([parsed.scheme, parsed.netloc])
        return False
    except Exception:
        return False

def download_image(url, save_dir):
    """Belirtilen URL'den resmi indir ve kaydet
    
    Args:
        url (str): Resim URL'si
        save_dir (str): Resmin kaydedileceği dizin
    Returns:
        str: Kaydedilen dosyanın yolu veya None (hata durumunda)
    """
    try:
        # URL'yi kontrol et ve tam URL oluştur
        if not url.startswith(('http://', 'https://')):
            return None
            
        # Resim dosyasını indir
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Dosya adını URL'den al ve temizle
        filename = os.path.basename(urlparse(url).path)
        filename = re.sub(r'[^\w\-_.]', '', filename)
        if not filename:
            filename = f'image_{int(time.time())}.jpg'
            
        # Dosya yolunu oluştur ve kaydet
        filepath = os.path.join(save_dir, filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filepath
    except Exception as e:
        print(f'Resim indirme hatası ({url}): {str(e)}')
        return None

def web_scraper(url, selectors=None, proxy=None, download_images=False):
    """Belirtilen URL'den veri çeken gelişmiş fonksiyon
    
    Args:
        url (str): Veri çekilecek URL
        selectors (dict): HTML elementlerini seçmek için kullanılacak CSS seçiciler
        proxy (dict): Proxy ayarları (örn: {'http': 'http://proxy.example.com:8080'})
    """
    try:
        # Rate limiting - aşırı istekleri önlemek için
        time.sleep(1)
        
        # Web sitesine GET isteği gönder
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Proxy kullanımı
        if proxy:
            response = requests.get(url, headers=headers, proxies=proxy)
        else:
            response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # HTML içeriğini parse et
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Varsayılan veya özel seçicilerle veri çekme
        if not selectors:
            selectors = {
                'title': 'title',
                'paragraphs': 'p',
                'links': 'a'
            }
        
        data = {
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'title': soup.select_one(selectors['title']).string if soup.select_one(selectors['title']) else 'Başlık bulunamadı',
            'paragraphs': [p.text.strip() for p in soup.select(selectors['paragraphs'])[:5]],
            'links': [{'text': a.text.strip(), 'href': a.get('href')} 
                      for a in soup.select(selectors['links'])[:10] if a.get('href')]
        }
        
        # Resim indirme özelliği aktifse
        if download_images:
            # pictures klasörünü oluştur
            pictures_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pictures')
            os.makedirs(pictures_dir, exist_ok=True)
            
            # Resimleri bul ve indir
            images = []
            for img in soup.find_all('img'):
                img_url = img.get('src')
                if img_url:
                    # Göreceli URL'leri tam URL'ye çevir
                    img_url = urljoin(url, img_url)
                    # Resmi indir
                    saved_path = download_image(img_url, pictures_dir)
                    if saved_path:
                        images.append({
                            'original_url': img_url,
                            'saved_path': saved_path
                        })
            
            data['images'] = images
        
        return data
        
    except requests.exceptions.RequestException as e:
        return {'error': f'Bağlantı hatası: {str(e)}'}
    except Exception as e:
        return {'error': f'Beklenmeyen hata: {str(e)}'}

def save_data(data, filename='scraping_results', format='json'):
    """Çekilen veriyi belirtilen formatta kaydet
    
    Args:
        data: Kaydedilecek veri
        filename (str): Dosya adı (uzantısız)
        format (str): Kayıt formatı ('json' veya 'csv')
    """
    try:
        if format.lower() == 'json':
            with open(f'{filename}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f'\nVeriler {filename}.json dosyasına kaydedildi.')
        
        elif format.lower() == 'csv':
            # CSV için düz veri yapısı oluştur
            flat_data = [{
                'url': item['url'],
                'timestamp': item['timestamp'],
                'title': item['title'],
                'paragraphs': '\n'.join(item['paragraphs']),
                'links': '\n'.join([f"{link['text']} ({link['href']})" for link in item['links']])
            } for item in data] if isinstance(data, list) else [data]
            
            with open(f'{filename}.csv', 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=flat_data[0].keys())
                writer.writeheader()
                writer.writerows(flat_data)
            print(f'\nVeriler {filename}.csv dosyasına kaydedildi.')
        
        else:
            raise ValueError(f'Desteklenmeyen format: {format}')
            
    except Exception as e:
        print(f'Dosya kaydetme hatası: {str(e)}')

def scrape_multiple_urls(urls, selectors=None, proxy=None, download_images=False):
    """Birden fazla URL'den veri çek"""
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(web_scraper, url, selectors, proxy, download_images) for url in urls]
        for future in futures:
            try:
                result = future.result()
                if 'error' not in result:
                    results.append(result)
            except Exception as e:
                print(f'URL işleme hatası: {str(e)}')
    return results

def print_banner():
    banner = r'''
      _      __    __     ____                         
     | | /| / /__ / /    / __/__________ ____  ___ ____
     | |/ |/ / -_) _ \  _\ \/ __/ __/ _ `/ _ \/ -_) __/
     |__/|__/\__/_.__/ /___/\__/_/  \_,_/ .__/\__/_/   
                                       /_/             
    '''
    print(banner)

def main():
    print_banner()
    while True:
        print('\nGelişmiş Web Scraping Aracı')
        print('-' * 30)
        print("1. Tek URL'den veri çek")
        print("2. Çoklu URL'lerden veri çek")
        print('3. Özel seçicilerle veri çek')
        print('4. Proxy ile veri çek')
        print('5. Çıkış')
        
        choice = input('\nSeçiminiz (1-5): ')
        
        if choice == '5':
            print('\nProgram sonlandırılıyor...')
            break
            
        elif choice == '1':
            while True:
                url = input('\nURL (örn: https://example.com): ')
                if not url:
                    print('URL boş olamaz!')
                    continue
                if not validate_url(url):
                    print('Geçersiz URL formatı! Lütfen geçerli bir URL girin.')
                    continue
                break
            data = web_scraper(url)
            
        elif choice == '2':
            urls = []
            print("\nURL'leri girin (bitirmek için boş bırakın):")
            while True:
                url = input('URL: ')
                if not url:
                    if not urls:
                        print('En az bir URL girmelisiniz!')
                        continue
                    break
                if not validate_url(url):
                    print('Geçersiz URL formatı! Bu URL atlanıyor.')
                    continue
                if url in urls:
                    print('Bu URL zaten listeye eklenmiş!')
                    continue
                urls.append(url)
                print(f'URL eklendi. Toplam: {len(urls)}')
            data = scrape_multiple_urls(urls)
            
        elif choice == '3':
            while True:
                url = input('\nURL (örn: https://example.com): ')
                if not url:
                    print('URL boş olamaz!')
                    continue
                if not validate_url(url):
                    print('Geçersiz URL formatı! Lütfen geçerli bir URL girin.')
                    continue
                break
            
            print('\nÖzel seçicileri girin (örn: title=h1, paragraphs=div.content p)')
            print('Not: Boş bırakırsanız varsayılan seçiciler kullanılacak.')
            selectors = {}
            for elem in ['title', 'paragraphs', 'links']:
                selector = input(f'{elem} için seçici: ')
                if selector:
                    selectors[elem] = selector
            data = web_scraper(url, selectors)
            
        elif choice == '4':
            while True:
                url = input('\nURL (örn: https://example.com): ')
                if not url:
                    print('URL boş olamaz!')
                    continue
                if not validate_url(url):
                    print('Geçersiz URL formatı! Lütfen geçerli bir URL girin.')
                    continue
                break
                
            proxy_url = input('Proxy URL (örn: http://proxy.example.com:8080): ')
            if proxy_url and not validate_url(proxy_url):
                print('Geçersiz proxy URL formatı! Proxy kullanılmayacak.')
                proxy = None
            else:
                proxy = {'http': proxy_url, 'https': proxy_url} if proxy_url else None
            data = web_scraper(url, proxy=proxy)
            
        else:
            print('\nGeçersiz seçim!')
            continue
            
        if isinstance(data, list):
            print(f"\n{len(data)} URL'den veri çekildi.")
        elif 'error' in data:
            print(f'\nHata: {data["error"]}')
            continue
        else:
            print('\nÇekilen Veriler:')
            print(f'Başlık: {data["title"]}')
            print(f'Paragraf sayısı: {len(data["paragraphs"])}')
            print(f'Link sayısı: {len(data["links"])}')
        
        format_choice = input('\nKayıt formatı (json/csv): ').lower()
        if format_choice in ['json', 'csv']:
            save_data(data, format=format_choice)
        else:
            print('Geçersiz format! Varsayılan olarak JSON kullanılıyor...')
            save_data(data)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Gelişmiş Web Scraping Aracı')
    parser.add_argument('url', nargs='?', help='Veri çekilecek URL')
    parser.add_argument('-u', '--urls', nargs='+', help='Birden fazla URL')
    parser.add_argument('-p', '--picture', action='store_true', help='Resimleri indir')
    parser.add_argument('-s', '--selector', help='Özel CSS seçici (örn: title=h1,paragraphs=div.content p)')
    parser.add_argument('--proxy', help='Proxy URL (örn: http://proxy.example.com:8080)')
    return parser.parse_args()

def process_selector_arg(selector_str):
    if not selector_str:
        return None
    try:
        selectors = {}
        for item in selector_str.split(','):
            key, value = item.split('=')
            selectors[key.strip()] = value.strip()
        return selectors
    except:
        return None

if __name__ == '__main__':
    args = parse_arguments()
    
    if args.url or args.urls:
        # Proxy ayarlarını hazırla
        proxy = {'http': args.proxy, 'https': args.proxy} if args.proxy else None
        
        # Seçicileri işle
        selectors = process_selector_arg(args.selector)
        
        # Tek URL veya çoklu URL işleme
        if args.urls:
            urls = [url for url in args.urls if validate_url(url)]
            if urls:
                data = scrape_multiple_urls(urls, selectors, proxy, args.picture)
            else:
                print('Geçerli URL bulunamadı!')
                exit(1)
        else:
            if validate_url(args.url):
                data = web_scraper(args.url, selectors, proxy, args.picture)
            else:
                print('Geçersiz URL formatı!')
                exit(1)
        
        # Sonuçları kaydet
        if isinstance(data, list):
            print(f"\n{len(data)} URL'den veri çekildi.")
        elif 'error' in data:
            print(f'\nHata: {data["error"]}')
            exit(1)
        else:
            print('\nÇekilen Veriler:')
            print(f'Başlık: {data["title"]}')
            print(f'Paragraf sayısı: {len(data["paragraphs"])}')
            print(f'Link sayısı: {len(data["links"])}')
            if args.picture and 'images' in data:
                print(f'İndirilen resim sayısı: {len(data["images"])}')
        
        save_data(data)
    else:
        main()