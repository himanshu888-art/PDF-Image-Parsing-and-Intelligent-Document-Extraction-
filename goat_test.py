import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pandas as pd
from urllib.parse import urlparse, parse_qs
import tkinter as tk


# -----------------------------
# 1) CLEAN GOOGLE REDIRECT URL
# -----------------------------
def clean_google_url(raw_url):
    if raw_url.startswith("https://www.google.com/url?"):
        parsed_url = urlparse(raw_url)
        actual_url = parse_qs(parsed_url.query).get('q', [''])[0]
        return actual_url
    return raw_url


# -----------------------------
# 2) CAPTCHA DETECTION
# -----------------------------
def is_captcha(driver):
    try:
        page = driver.page_source.lower()
        return (
            "unusual traffic" in page or
            "recaptcha" in page or
            "detected unusual" in page or
            "solve the captcha" in page
        )
    except:
        return False


# -----------------------------
# 3) POPUP WHEN CAPTCHA HAPPENS
# -----------------------------
def show_captcha_popup():
    root = tk.Tk()
    root.title("Captcha Detected")
    root.geometry("350x150")

    label = tk.Label(
        root,
        text="Captcha detected!\nPlease solve it in the browser.\nClick Continue after solving.",
        font=("Arial", 11),
        justify="center"
    )
    label.pack(pady=15)

    btn = tk.Button(root, text="Continue", command=root.destroy, width=15)
    btn.pack(pady=10)

    root.mainloop()


# -----------------------------
# 4) SAVE CHECKPOINT
# -----------------------------
def save_checkpoint(all_data, all_sources, filename="checkpoint_google_jobs.xlsx"):
    final_data = []
    for job in all_data:
        full_row = job.copy()
        for src in all_sources:
            if src not in full_row:
                full_row[src] = ''
        final_data.append(full_row)

    ordered_columns = ['Search_Company', 'Job_Company', 'Title',
                       'Location', 'Source', 'URL', 'Final URL'] + sorted(all_sources)

    df = pd.DataFrame(final_data)[ordered_columns]
    df.to_excel(filename, index=False)
    print(f"💾 Checkpoint saved to {filename}")


# -----------------------------
# 5) LOAD INPUT EXCEL
# -----------------------------
input_df = pd.read_excel(r"ADD your input addresst\input.xlsx")
company_names = input_df['company name'].dropna().unique()

all_data = []
all_sources = set()


# -----------------------------
# 6) SETUP CHROME (UC)
# -----------------------------
options = uc.ChromeOptions()
driver = uc.Chrome(version_main=139, options=options)
wait = WebDriverWait(driver, 10)


# -----------------------------
# 7) MAIN SCRAPING LOOP
# -----------------------------
for company in company_names:
    print(f"\n🔍 Searching jobs for: {company}")

    search_url = f"https://www.google.com/search?q={company}+jobs&udm=8"
    driver.get(search_url)

    # 🔐 CAPTCHA CHECK AT COMPANY START
    if is_captcha(driver):
        print("⛔ CAPTCHA DETECTED! Saving checkpoint...")
        save_checkpoint(all_data, all_sources)
        show_captcha_popup()
        print("✅ Resuming...")

    # SCROLL TO LOAD ALL JOBS
    prev_count = 0
    same_count_retries = 0
    max_retries = 5

    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)

        titles = driver.find_elements(By.XPATH, '//div[@class="tNxQIb PUpOsf"]')
        current_count = len(titles)

        if current_count == prev_count:
            same_count_retries += 1
        else:
            same_count_retries = 0
            prev_count = current_count

        if same_count_retries >= max_retries:
            break

    print(f"✅ Found {prev_count} jobs for {company}")

    # -------- JOB LOOP --------
    for i in range(prev_count):

        # CAPTCHA CHECK INSIDE JOB LOOP
        if is_captcha(driver):
            print("⛔ CAPTCHA DETECTED DURING JOB SCRAPING!")
            save_checkpoint(all_data, all_sources)
            show_captcha_popup()
            print("✅ Continuing extraction...")

        try:
            # REFRESH ELEMENTS
            titles = driver.find_elements(By.XPATH, '//div[@class="tNxQIb PUpOsf"]')
            job_companies = driver.find_elements(By.XPATH, '//div[@class="wHYlTd MKCbgd a3jPc"]')
            locations_sources = driver.find_elements(By.XPATH, '//div[@class="wHYlTd FqK3wc MKCbgd"]')
            links = driver.find_elements(By.XPATH, '//a[@class="MQUd2b"]')

            if i >= len(titles):
                break

            title = titles[i].text.strip()
            job_company = job_companies[i].text.strip() if i < len(job_companies) else ''

            location = sources = ''
            if i < len(locations_sources):
                loc_src = locations_sources[i].text.split("•")
                location = loc_src[0].strip()
                if len(loc_src) > 1:
                    sources = loc_src[1].strip()

            raw_url = links[i].get_attribute('href') if i < len(links) else ''
            url = clean_google_url(raw_url)
            url_suffix = raw_url.split("&udm=")[1] if "&udm=" in raw_url else ''
            final_url = f"https://www.google.com/search?q={company}+jobs&udm={url_suffix}" if url_suffix else ''

            job_data = {
                'Search_Company': company,
                'Job_Company': job_company,
                'Title': title,
                'Location': location,
                'Source': sources,
                'URL': url,
                'Final URL': final_url
            }

            # CLICK JOB PANEL
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", titles[i])
            time.sleep(3)

            try:
                titles[i].click()
            except:
                driver.execute_script("arguments[0].click();", titles[i])

            time.sleep(5)

            # WAIT FOR JOB PANEL
            wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="NgUYpe"]')))

            # APPLY SOURCES (MULTIPLE)
            try:
                apply_buttons = driver.find_elements(By.XPATH, '//a[contains(@title, "Apply") or contains(text(), "Apply on")]')
                for btn in apply_buttons:
                    source_text = btn.get_attribute('title') or btn.text
                    source_clean = source_text.replace("Apply on", "").replace("Apply directly on", "").strip()
                    apply_href = btn.get_attribute('href')
                    if source_clean:
                        job_data[source_clean] = apply_href
                        all_sources.add(source_clean)
            except:
                pass

            print(f"✅ Processed job {i+1}/{prev_count} — {title[:50]}")

        except Exception as e:
            print(f"⚠️ Error at job {i+1}: {e}")

        all_data.append(job_data)


# -----------------------------
# 8) FINAL SAVE
# -----------------------------
driver.quit()

final_data = []
for job in all_data:
    full_row = job.copy()
    for src in all_sources:
        if src not in full_row:
            full_row[src] = ''
    final_data.append(full_row)

ordered_columns = ['Search_Company', 'Job_Company', 'Title',
                   'Location', 'Source', 'URL', 'Final URL'] + sorted(all_sources)

df = pd.DataFrame(final_data)[ordered_columns]
output_path = 'Google_Jobs_Without_JD.xlsx'
df.to_excel(output_path, index=False)

print(f"\n✅ All done. {len(df)} jobs saved to {output_path}.")

