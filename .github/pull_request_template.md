<!-- Disimpan di .github/pull_request_template.md, GitHub mengisi deskripsi pull request baru dengan template ini -->
## Apa yang berubah
<!-- Satu atau dua kalimat. Sertakan nomor issue jika ada. -->

## Kenapa
<!-- Masalah yang diselesaikan atau kebutuhan bisnisnya. -->

## Cara mengecek
<!-- Langkah yang bisa diikuti reviewer: endpoint, data contoh, perintah. -->

## Checklist
- [ ] Test baru atau test yang diubah ikut di pull request ini
- [ ] `ruff check .` dan `pytest` hijau
- [ ] Tidak ada secret, password, atau token di kode maupun log
- [ ] Endpoint baru punya pengecekan login dan scope
- [ ] Perubahan database punya index yang dibutuhkan, tanpa N+1 query
- [ ] README atau ADR diperbarui jika ada perubahan cara menjalankan atau keputusan arsitektur
