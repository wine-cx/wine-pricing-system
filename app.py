import streamlit as st
import pandas as pd
import os
from datetime import datetime
import base64
import requests
from io import BytesIO
import chardet

# ========== 初始化文件夹 ==========
UPLOAD_DIR = "data_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ========== GitHub 自动保存函数 ==========
def save_to_github(filename, content):
    try:
        github_token = st.secrets["GITHUB_TOKEN"]
        repo_owner = st.secrets["REPO_OWNER"]
        repo_name = st.secrets["REPO_NAME"]
        branch = st.secrets.get("BRANCH", "main")

        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/data_uploads/{filename}"

        get_headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        # 检查文件是否已存在（获取 SHA）
        get_resp = requests.get(url, headers=get_headers)
        if get_resp.status_code == 200:
            sha = get_resp.json()["sha"]
        else:
            sha = None

        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        payload = {
            "message": f"上传报价文件 {filename}",
            "content": content_b64,
            "branch": branch
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(url, headers=get_headers, json=payload)

        if put_resp.status_code in [200, 201]:
            st.success("✅ 文件已成功保存至 GitHub")
        else:
            st.warning(f"⚠️ GitHub 保存失败：{put_resp.status_code} - {put_resp.text}")
    except Exception as e:
        st.warning(f"⚠️ GitHub 保存异常：{e}")

# ========== 动态读取字段模板 ==========
@st.cache_data
def load_column_template(file_path="字段模板.xlsx"):
    try:
        df = pd.read_excel(file_path)
        column_map = {}
        for _, row in df.iterrows():
            supplier = row["供货商名"]
            mapping = {}
            for field in [
                "酒名英文字段", "酒名中文字段", "年份字段",
                "单价字段", "散支字段", "整箱字段",
                "整箱规格字段", "净含量字段", "官网链接"
            ]:
                if pd.notna(row.get(field, "")):
                    mapping[field] = row[field]
            if mapping:
                column_map[supplier] = mapping
        return column_map
    except Exception as e:
        st.error(f"字段模板读取失败：{e}")
        return {}

# ========== 加载用户账号 ==========
@st.cache_data
def load_users(file_path="users.xlsx"):
    try:
        df = pd.read_excel(file_path)
        return df.set_index("用户名").to_dict("index")
    except Exception as e:
        st.error(f"用户账号读取失败：{e}")
        return {}

# ========== 智能检测文件编码 ==========
def detect_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        rawdata = f.read(10000)  # 读取前10000字节用于检测编码
    result = chardet.detect(rawdata)
    return result['encoding']

# ========== 读取上传的文件 ==========
def load_uploaded_data():
    all_files = [f for f in os.listdir(UPLOAD_DIR) if f.endswith((".csv", ".xlsx"))]
    all_data = []
    for file in all_files:
        try:
            file_path = os.path.join(UPLOAD_DIR, file)
            if file.endswith('.csv'):
                # 自动检测编码
                encoding = detect_file_encoding(file_path)
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    st.toast(f"成功读取 {file} (编码: {encoding})")
                except Exception as e:
                    st.warning(f"首次尝试 {encoding} 编码失败，尝试备用编码...")
                    # 备用编码尝试
                    encodings = ['utf-8', 'gbk', 'big5', 'utf-16', 'iso-8859-1']
                    for enc in encodings:
                        try:
                            df = pd.read_csv(file_path, encoding=enc)
                            st.toast(f"成功用备用编码 {enc} 读取 {file}")
                            break
                        except:
                            continue
                    else:
                        raise ValueError(f"无法读取文件 {file} - 尝试了所有编码")
            else:  # Excel文件
                df = pd.read_excel(file_path)
            
            all_data.append(df)
        except Exception as e:
            st.error(f"读取文件 {file} 失败: {e}")
            continue
    return all_data

users = load_users()
column_template = load_column_template()

# ========== 登录模块 ==========
st.title("🍷 红酒查价系统 - 登录")

if "user" not in st.session_state:
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")

        if submitted:
            if username in users and users[username]["密码"] == password:
                st.session_state.user = username
                st.session_state.role = users[username]["角色"]
                st.rerun()
            else:
                st.error("用户名或密码错误")

# ========== 主系统页面 ==========
if "user" in st.session_state:
    st.success(f"欢迎你，{st.session_state.user}（{st.session_state.role}）")
    role = st.session_state.role

    supplier = st.selectbox("请选择上传的供货商：", [""] + list(column_template.keys()))
    file = st.file_uploader("上传报价文件（支持 .xlsx 或 .csv）", type=["xlsx", "csv"])
    st.caption("注意：CSV文件建议使用UTF-8编码，如遇中文乱码请尝试另存为UTF-8格式")

    if supplier and file:
        try:
            # 根据文件类型使用不同读取方式
            if file.name.endswith('.csv'):
                # 读取CSV文件内容用于编码检测
                content = file.getvalue()
                result = chardet.detect(content)
                encoding = result['encoding']
                
                # 尝试读取
                try:
                    file.seek(0)  # 重置文件指针
                    df_raw = pd.read_csv(file, encoding=encoding)
                    st.toast(f"检测到编码: {encoding}，成功读取CSV文件")
                except Exception as e:
                    st.warning(f"编码 {encoding} 读取失败，尝试备用编码...")
                    encodings = ['utf-8', 'gbk', 'big5', 'utf-16', 'iso-8859-1']
                    for enc in encodings:
                        try:
                            file.seek(0)
                            df_raw = pd.read_csv(file, encoding=enc)
                            st.toast(f"成功用备用编码 {enc} 读取文件")
                            break
                        except:
                            continue
                    else:
                        raise ValueError("无法读取CSV文件 - 请检查文件编码")
            else:  # Excel文件
                df_raw = pd.read_excel(file)
            
            field_map = column_template[supplier]

            renamed = {}
            for std_col, orig_col in field_map.items():
                if "+" in str(orig_col):
                    parts = [df_raw.get(p.strip(), "") for p in orig_col.split("+")]
                    renamed[std_col] = parts[0].astype(str)
                    for part in parts[1:]:
                        renamed[std_col] += part.astype(str)
                elif orig_col in df_raw.columns:
                    renamed[std_col] = df_raw[orig_col]
                else:
                    renamed[std_col] = ""

            df_clean = pd.DataFrame(renamed)
            df_clean["供货商"] = supplier
            df_clean["供货商代码"] = supplier.split("(")[-1].replace(")", "")
            df_clean["上传时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            df_clean["官网链接"] = field_map.get("官网链接", "")

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            filename = f"{supplier}_{timestamp}.csv"
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            # 统一保存为UTF-8 with BOM格式
            df_clean.to_csv(filepath, index=False, encoding='utf-8-sig')
            save_to_github(filename, df_clean.to_csv(index=False, encoding='utf-8-sig'))

            st.success(f"✅ 成功读取并映射字段，共 {len(df_clean)} 条记录，已保存为 {filename}")
            st.dataframe(df_clean)

        except Exception as e:
            st.error(f"❌ 文件处理失败：{e}")
    elif file and not supplier:
        st.warning("⚠️ 请先选择供货商再上传文件。")

    # ========== 汇总展示 ==========
    all_data = load_uploaded_data()
    if all_data:
        df_all = pd.concat(all_data, ignore_index=True)
        st.subheader("📊 汇总比价结果")

        keyword = st.text_input("🔍 输入关键词（酒名/年份/供货商）进行筛选：")
        if keyword:
            df_all = df_all[df_all.astype(str).apply(lambda row: row.str.contains(keyword, case=False)).any(axis=1)]

        if set(["酒名英文字段", "年份字段", "单价字段"]).issubset(df_all.columns):
            df_all["比价键"] = df_all["酒名英文字段"].astype(str) + "_" + df_all["年份字段"].astype(str)
            df_all["单价字段"] = pd.to_numeric(df_all["单价字段"], errors="coerce")
            if not df_all["单价字段"].isna().all():
                idx_min_price = df_all.groupby("比价键")["单价字段"].idxmin()
                df_all["是否最低价"] = ""
                df_all.loc[idx_min_price, "是否最低价"] = "✅ 最低"
            else:
                df_all["是否最低价"] = ""
        else:
            st.warning("比价功能依赖字段：酒名英文字段、年份字段、单价字段，请确保它们存在。")

        def render_link(row):
            url = row.get("官网链接", "")
            return f'<a href="{url}" target="_blank">🔗 官网</a>' if url else ""

        df_all["跳转官网"] = df_all.apply(render_link, axis=1)

        if role == "销售":
            columns_to_show = [
                "酒名英文字段", "酒名中文字段", "年份字段", "单价字段",
                "散支字段", "整箱字段", "整箱规格字段", "净含量字段",
                "是否最低价", "供货商代码"
            ]
        else:
            columns_to_show = df_all.columns.tolist()

        st.write("✅ 下方可点击跳转供货商官网")
        st.write(df_all[columns_to_show].to_html(escape=False), unsafe_allow_html=True)

        def convert_df(df):
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.drop(columns=["跳转官网"], errors="ignore").to_excel(writer, index=False, sheet_name='报价比价')
                writer.save()
            return output.getvalue()

        excel_bytes = convert_df(df_all[columns_to_show])
        st.download_button(
            label="📥 下载比价结果 Excel",
            data=excel_bytes,
            file_name="比价结果.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
