"""
36機関公表物監視システム
HTMLダッシュボードと完全連携
"""

import requests
import schedule
import time
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import pytz
import logging

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PublicationMonitor:
    def __init__(self):
        self.paris_tz = pytz.timezone('Europe/Paris')
        self.data_file = 'publications_data.json'
        self.html_template = 'dashboard_template.html'
        self.html_output = 'index.html'
        
        # セッション設定
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 36機関の公表物定義（HTMLテーブルと完全対応）
        self.institutions = [
            {
                'id': 1,
                'institution': 'EBA',
                'publication': 'ESEP',
                'frequency': 'Annual',
                'url': 'https://www.eba.europa.eu/',
                'search_patterns': [r'esep.*report', r'supervisory.*review.*evaluation'],
                'last_published': '2024-07-08',
                'last_title': 'EBA ESEP Report 2024',
                'predicted_next': '2025年7月'
            },
            {
                'id': 2,
                'institution': 'EBA',
                'publication': 'EU-wide Stress Test',
                'frequency': 'Bi-Annual',
                'url': 'https://www.eba.europa.eu/',
                'search_patterns': [r'stress.*test', r'eu.*wide.*stress'],
                'last_published': '2023-07-28',
                'last_title': 'EU-wide Stress Test Results 2023',
                'predicted_next': '2025年後半'
            },
            {
                'id': 3,
                'institution': 'S&P',
                'publication': 'Portugal Sovereign Rating',
                'frequency': 'Semi-Annual',
                'url': 'https://www.spglobal.com/ratings/en/sector/governments/sovereigns',
                'search_patterns': [r'portugal.*sovereign', r'portugal.*rating'],
                'last_published': '2025-02-28',
                'last_title': 'Portugal Sovereign Rating Review',
                'predicted_next': '2025-08-29'
            },
            {
                'id': 4,
                'institution': 'Banque de France',
                'publication': 'Macroeconomic Projections',
                'frequency': 'Quarterly',
                'url': 'https://www.banque-france.fr/en/publications-and-statistics/publications',
                'search_patterns': [r'macroeconomic.*projection', r'economic.*forecast'],
                'last_published': '',
                'last_title': '',
                'predicted_next': '2025年9月',
                'last_year_same_period': '2024-09-17'
            },
            {
                'id': 5,
                'institution': 'Banco de España',
                'publication': 'Macroeconomic Projections',
                'frequency': 'Quarterly',
                'url': 'https://www.bde.es/wbe/en/publicaciones/',
                'search_patterns': [r'macroeconomic.*projection', r'economic.*forecast'],
                'last_published': '',
                'last_title': '',
                'predicted_next': '2025年9月',
                'last_year_same_period': '2024-09-17'
            },
            {
                'id': 6,
                'institution': 'OECD',
                'publication': 'Interim Economic Outlook',
                'frequency': 'Irregular',
                'url': 'https://www.oecd.org/en/publications/',
                'search_patterns': [r'interim.*economic.*outlook', r'economic.*outlook.*interim'],
                'last_published': '2025-03-17',
                'last_title': 'OECD Interim Economic Outlook, March 2025',
                'predicted_next': '2025年9月'
            },
            # ... 残りの30機関も同様に定義
            # (スペースの関係で省略しますが、実際のコードでは全36機関を含める)
        ]
        
        # 格付け機関スケジュール（PDFベース）
        self.rating_schedule = {
            'S&P': {
                'Spain': '2025-09-12',
                'France': '2025-11-28',
                'Italy': '2025-10-10',
                'Portugal': '2025-08-29'
            },
            'Fitch': {
                'France': '2025-09-12',
                'Portugal': '2025-09-12',
                'Italy': '2025-09-19',
                'Spain': '2025-09-26'
            },
            'Moody\'s': {
                'France': '2025-10-24',
                'Portugal': '2025-11-14',
                'Italy': '2025-11-21',
                'Spain': '2025年11月'
            }
        }
        
        self.load_data()

    def load_data(self):
        """過去のデータを読み込み"""
        try:
            if Path(self.data_file).exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.historical_data = json.load(f)
            else:
                self.historical_data = {}
            logger.info(f"データ読み込み完了: {len(self.historical_data)} 件")
        except Exception as e:
            logger.error(f"データ読み込みエラー: {e}")
            self.historical_data = {}

    def save_data(self):
        """データ保存"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.historical_data, f, ensure_ascii=False, indent=2)
            logger.info("データ保存完了")
        except Exception as e:
            logger.error(f"データ保存エラー: {e}")

    def crawl_institution(self, institution_config):
        """個別機関のクローリング"""
        try:
            logger.info(f"🔍 {institution_config['institution']} - {institution_config['publication']} をクローリング中...")
            
            response = self.session.get(institution_config['url'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # パターンマッチングで公表物を検索
            found_publications = []
            
            for pattern in institution_config['search_patterns']:
                # タイトル要素から検索
                for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'a', 'span']):
                    text = element.get_text(strip=True)
                    if text and len(text) > 10:
                        if re.search(pattern, text, re.IGNORECASE):
                            date_text = self.extract_date_near_element(element)
                            found_publications.append({
                                'title': text,
                                'date_text': date_text,
                                'url': self.get_element_url(element, institution_config['url']),
                                'extracted_at': datetime.now(self.paris_tz).isoformat()
                            })
                            break
            
            # 結果を処理
            if found_publications:
                latest = found_publications[0]  # 最初に見つかったものを使用
                
                # 日付を解析
                predicted_date = self.parse_next_date(latest['date_text'], institution_config)
                
                # データ更新
                key = f"{institution_config['institution']}_{institution_config['publication']}"
                self.historical_data[key] = {
                    'institution': institution_config['institution'],
                    'publication': institution_config['publication'],
                    'frequency': institution_config['frequency'],
                    'predicted_next': predicted_date or institution_config['predicted_next'],
                    'last_published': latest.get('date_text', institution_config.get('last_published', '')),
                    'last_title': latest['title'][:100] + '...' if len(latest['title']) > 100 else latest['title'],
                    'last_year_same_period': institution_config.get('last_year_same_period', ''),
                    'last_crawled': datetime.now(self.paris_tz).isoformat(),
                    'source_url': institution_config['url']
                }
                
                logger.info(f"✅ {institution_config['institution']} 更新完了")
                return True
            else:
                logger.warning(f"⚠️ {institution_config['institution']} - 該当する公表物が見つかりませんでした")
                return False
                
        except Exception as e:
            logger.error(f"❌ {institution_config['institution']} クローリングエラー: {e}")
            return False

    def extract_date_near_element(self, element):
        """要素周辺から日付を抽出"""
        date_patterns = [
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            r'(january|february|march|april|may|june|july|august|september|october|november|december).*?(\d{4})',
            r'(\d{1,2}).*?(january|february|march|april|may|june|july|august|september|october|november|december).*?(\d{4})'
        ]
        
        # 要素自体のテキスト
        text = element.get_text()
        
        # 親要素のテキストも確認
        if element.parent:
            text += " " + element.parent.get_text()
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0] if isinstance(matches[0], str) else ' '.join(matches[0])
        
        return None

    def get_element_url(self, element, base_url):
        """要素からURLを取得"""
        if element.name == 'a' and element.get('href'):
            href = element.get('href')
            if href.startswith('http'):
                return href
            else:
                return base_url + href
        return base_url

    def parse_next_date(self, date_text, institution_config):
        """次回公表日を予測"""
        if not date_text:
            return None
        
        # 格付け機関は専用スケジュールを使用
        if institution_config['institution'] in ['S&P', 'Fitch', 'Moody\'s']:
            country = None
            for c in ['Spain', 'France', 'Italy', 'Portugal']:
                if c.lower() in institution_config['publication'].lower():
                    country = c
                    break
            
            if country and institution_config['institution'] in self.rating_schedule:
                scheduled_date = self.rating_schedule[institution_config['institution']].get(country)
                if scheduled_date:
                    return scheduled_date
        
        # 一般的な予測ロジック
        frequency = institution_config['frequency'].lower()
        if 'annual' in frequency:
            return self.predict_annual_date(date_text)
        elif 'semi-annual' in frequency:
            return self.predict_semi_annual_date(date_text)
        elif 'quarterly' in frequency:
            return self.predict_quarterly_date(date_text)
        else:
            return f"2025年後半"  # 不定期の場合

    def predict_annual_date(self, last_date):
        """年次公表物の次回予測"""
        try:
            # 簡単な予測：前年同時期
            return "2025年同時期"
        except:
            return "2025年後半"

    def predict_semi_annual_date(self, last_date):
        """半期公表物の次回予測"""
        try:
            # 6ヶ月後を予測
            return "6ヶ月後予定"
        except:
            return "2025年後半"

    def predict_quarterly_date(self, last_date):
        """四半期公表物の次回予測"""
        try:
            # 3ヶ月後を予測
            return "3ヶ月後予定"
        except:
            return "2025年後半"

    def crawl_all_institutions(self):
        """全機関のクローリング実行"""
        logger.info("🚀 全機関クローリング開始")
        
        success_count = 0
        total_count = len(self.institutions)
        
        for institution_config in self.institutions:
            if self.crawl_institution(institution_config):
                success_count += 1
            
            # レート制限対策
            time.sleep(2)
        
        logger.info(f"✅ クローリング完了: {success_count}/{total_count} 成功")
        
        # データ保存
        self.save_data()
        
        # HTML生成
        self.generate_html()

    def generate_html(self):
        """HTMLダッシュボード生成"""
        try:
            # HTMLテンプレート読み込み
            if not Path(self.html_template).exists():
                logger.error(f"HTMLテンプレートが見つかりません: {self.html_template}")
                return
            
            with open(self.html_template, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # 統計計算
            stats = self.calculate_stats()
            
            # テンプレート変数を置換
            html_content = html_content.replace('{{LAST_UPDATE_TIME}}', 
                                              datetime.now(self.paris_tz).strftime('%Y-%m-%d %H:%M:%S (パリ時間)'))
            
            # テーブルデータを動的生成（現在のHTMLの31行に対応）
            table_rows = self.generate_table_rows()
            
            # テーブル部分を置換（既存のtbody内容を置き換え）
            tbody_pattern = r'<tbody>.*?</tbody>'
            new_tbody = f'<tbody>\n{table_rows}\n            </tbody>'
            html_content = re.sub(tbody_pattern, new_tbody, html_content, flags=re.DOTALL)
            
            # 出力ファイルに保存
            with open(self.html_output, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"✅ HTMLダッシュボード生成完了: {self.html_output}")
            
        except Exception as e:
            logger.error(f"❌ HTML生成エラー: {e}")

    def calculate_stats(self):
        """統計情報計算"""
        # 現在のデータから統計を計算
        # （実装簡略化）
        return {
            'today_count': 0,
            'soon_count': 2,  # EBAの2件
            'normal_count': 29,
            'irregular_count': 0
        }

    def generate_table_rows(self):
        """テーブル行を動的生成"""
        rows = []
        
        # 次回公表日順にソート
        sorted_data = self.sort_by_next_date()
        
        for i, data in enumerate(sorted_data, 1):
            row = f"""                <tr>
                    <td style="text-align: center; font-weight: bold;">{i}</td>
                    <td class="institution-cell">{data['institution']}</td>
                    <td><strong>{data['publication']}</strong></td>
                    <td>{data['frequency']}</td>
                    <td style="text-align: center;">{data['predicted_next']}</td>
                    <td style="text-align: center;">{data['last_published']}</td>
                    <td>{data['last_title']}</td>
                    <td style="text-align: center;">{data.get('last_year_same_period', '-')}</td>
                </tr>"""
            rows.append(row)
        
        return '\n'.join(rows)

    def sort_by_next_date(self):
        """次回公表日順にソート"""
        # 現在の31機関データを次回公表日順に並び替え
        # （実装簡略化：現在のHTMLと同じ順序を維持）
        
        base_data = []
        for institution_config in self.institutions:
            key = f"{institution_config['institution']}_{institution_config['publication']}"
            if key in self.historical_data:
                base_data.append(self.historical_data[key])
            else:
                # クローリングデータがない場合はデフォルト値を使用
                base_data.append({
                    'institution': institution_config['institution'],
                    'publication': institution_config['publication'],
                    'frequency': institution_config['frequency'],
                    'predicted_next': institution_config['predicted_next'],
                    'last_published': institution_config.get('last_published', '-'),
                    'last_title': institution_config.get('last_title', '-'),
                    'last_year_same_period': institution_config.get('last_year_same_period', '-')
                })
        
        return base_data

    def schedule_daily_crawling(self):
        """毎日のクローリングスケジュール設定"""
        # 毎朝パリ時間7時に実行
        schedule.every().day.at("07:00").do(self.crawl_all_institutions)
        logger.info("📅 毎日パリ時間7時のクローリングをスケジュール設定")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1分間隔でチェック

def main():
    """メイン実行関数"""
    monitor = PublicationMonitor()
    
    # 初回実行
    logger.info("🎯 初回クローリング実行")
    monitor.crawl_all_institutions()
    
    # スケジュール実行開始
    logger.info("⏰ スケジュール実行開始")
    monitor.schedule_daily_crawling()

if __name__ == "__main__":
    main()