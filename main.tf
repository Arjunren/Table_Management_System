terraform {
  required_providers {
    railway = {
      source  = "terraform-community-providers/railway"
      version = "~> 0.6.2"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9.1"
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

resource "railway_variable_collection" "mysql_vars" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.mysql_db.id
  
  variables = [
    {
      name  = "MYSQL_ROOT_PASSWORD"
      value = "PlTLWwKtkioZFAhVQzsKEStRhheiGBBz"
    },
    {
      name  = "MYSQL_DATABASE"
      value = "railway"
    }
  ]
}

resource "railway_service" "flask_app" {
  project_id         = railway_project.table_management.id
  name               = "Table Management Web App"
  source_repo        = "Arjunren/Table_Management_System"
  source_repo_branch = "main"
}

resource "railway_variable_collection" "flask_vars" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  
  variables = [
    {
      name  = "Secret_Key"
      value = "SuperSecretKey123"
    },
    {
      name  = "MYSQLUSER"
      value = "root"
    },
    {
      name  = "MYSQLPASSWORD"
      value = "PlTLWwKtkioZFAhVQzsKEStRhheiGBBz"
    },
    {
      name  = "MYSQLDATABASE"
      value = "railway"
    },
    {
      name  = "MYSQLHOST"
      value = "mysql.railway.internal"
    },
    {
      name  = "MYSQLPORT"
      value = "3306"
    },
    {
      name  = "MYSQL_URL"
      value = "mysql://root:PlTLWwKtkioZFAhVQzsKEStRhheiGBBz@mysql.railway.internal:3306/railway"
    },
    {
      name  = "PORT"
      value = "5000"
    }
  ]
}

resource "time_sleep" "wait_for_deploy" {
  depends_on      = [railway_variable_collection.flask_vars]
  create_duration = "60s"
}

resource "railway_service_domain" "public_url" {
  environment_id = railway_project.table_management.default_environment.id
  service_id     = railway_service.flask_app.id
  subdomain      = "arjun-table-management" 
  depends_on     = [time_sleep.wait_for_deploy]
}