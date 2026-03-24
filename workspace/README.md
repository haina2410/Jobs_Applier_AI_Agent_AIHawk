# CV Workspace Guidelines

Thư mục này dùng để chứa dữ liệu ứng viên và các jobs đã crawl, phục vụ cho luồng filter & auto-customize CV.

## 1. Cấu trúc yêu cầu cho mỗi người

Để thêm một người vào hệ thống, tạo thư mục `workspace/STT_TÊN_NGƯỜI/cv/` và thêm 2 files bắt buộc:

- `CV.tex`: CV gốc của bạn (định dạng LaTeX).
- `cv_prompt.txt`: File cấu hình prompt chứa thông tin background của bạn (để Gemini biết cách chỉnh sửa phù hợp nội dung).

## 2. Dữ liệu crawled jobs

Tất cả files JSON chứa jobs crawled phải được đặt vào đúng đường dẫn:

- **LinkedIn**: `workspace/crawled_jobs/linkedin/linkedin_crawled_jobs.json`
- **Facebook**: `workspace/crawled_jobs/facebook/facebook_crawled_jobs.json`

## 3. Cách chạy luồng (Flow)

**Bước 1**: Khai báo keywords của bạn trong file `config_persons.yaml` (nằm chung thư mục với script này).

**Bước 2**: Tại thư mục `workspace`, chạy lệnh:

- **Preview jobs (không tạo file):** `python process_jobs.py --person TÊN_NGƯỜI --dry-run`
- **Chạy thực tế (customize CV):** `python process_jobs.py --person TÊN_NGƯỜI`

Kết quả sẽ sinh ra các thư mục `workspace/STT_TÊN_NGƯỜI/jobs/job_XX/` chứa file metadata, `CV_customized.tex` và `changes.md` báo cáo những điểm đã sửa.
