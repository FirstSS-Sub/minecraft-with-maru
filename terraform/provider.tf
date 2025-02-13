provider "google" {
  project = "minecraft-with-maru"
  region  = var.region
  credentials = file("../key.json")  # 既存のサービスアカウントキーを使用
}
