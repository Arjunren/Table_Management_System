terraform {
  required_providers {
    railway = {
      source  = "terraform-community-providers/railway"
      version = "~> 0.6.2"
    }
  }
}

provider "railway" {}

resource "railway_project" "table_management" {
  name        = "Table Management System"
  description = "Flask + MySQL Deployment for Grading"
}

resource "railway_service" "mysql_db" {
  project_id   = railway_project.table_management.id
  name         = "mysql"
  source_image = "mysql:8"
}

# Set up the core MySQL database credentials
resource "railway_variable" "mysql_root_password" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.mysql_db.id
  name           = "MYSQL_ROOT_PASSWORD"
  value          = "PlTLWwKtkioZFAhVQzsKEStRhheiGBBz"
}

resource "railway_variable" "mysql_database_name" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.mysql_db.id
  name           = "MYSQL_DATABASE"
  value          = "railway"
}

# 3. Deploy the Python Flask Web Application
resource "railway_service" "flask_app" {
  project_id         = railway_project.table_management.id
  name               = "Table Management Web App"
  source_repo        = "Arjunren/Table_Management_System"
  source_repo_branch = "main"
}

resource "railway_variable" "secret_key" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "Secret_Key"
  value          = "SuperSecretKey123"
}

resource "railway_variable" "app_mysql_user" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQLUSER"
  value          = "root"
}

resource "railway_variable" "app_mysql_password" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQLPASSWORD"
  value          = "PlTLWwKtkioZFAhVQzsKEStRhheiGBBz"
}

resource "railway_variable" "app_mysql_database" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQLDATABASE"
  value          = "railway"
}

resource "railway_variable" "app_mysql_host" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQLHOST"
  value          = "mysql.railway.internal" 
}

resource "railway_variable" "app_mysql_port" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQLPORT"
  value          = "3306"
}

resource "railway_variable" "mysql_url" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "MYSQL_URL"
  value          = "mysql://root:PlTLWwKtkioZFAhVQzsKEStRhheiGBBz@mysql.railway.internal:3306/railway"
}

resource "railway_variable" "port" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  name           = "PORT"
  value          = "5000"
}

resource "railway_service_domain" "public_url" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  subdomain      = "tms-arjunren-grading-v2" 
}