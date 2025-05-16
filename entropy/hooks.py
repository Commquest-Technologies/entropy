app_name = "entropy"
app_title = "Entropy"
app_publisher = "Commquest Technologies (Pty) Ltd."
app_description = "Entropy Customisation ERPNext Application"
app_email = "info@commquest.co.za"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "entropy",
# 		"logo": "/assets/entropy/logo.png",
# 		"title": "Entropy",
# 		"route": "/entropy",
# 		"has_permission": "entropy.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/entropy/css/entropy.css"
# app_include_js = "/assets/entropy/js/entropy.js"

# include js, css files in header of web template
# web_include_css = "/assets/entropy/css/entropy.css"
# web_include_js = "/assets/entropy/js/entropy.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "entropy/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "entropy/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "entropy.utils.jinja_methods",
# 	"filters": "entropy.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "entropy.install.before_install"
# after_install = "entropy.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "entropy.uninstall.before_uninstall"
# after_uninstall = "entropy.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "entropy.utils.before_app_install"
# after_app_install = "entropy.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "entropy.utils.before_app_uninstall"
# after_app_uninstall = "entropy.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "entropy.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# The important change - completely override the doctype classes
override_doctype_class = {
    "Customer": "entropy.utils.custom_naming.CustomCustomer",
    "Supplier": "entropy.utils.custom_naming.CustomSupplier"
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#     "Customer": {
#         "autoname": "entropy.utils.custom_naming.CustomCustomer.autoname",
#         "validate": "entropy.utils.custom_naming.CustomCustomer.validate"
#     },
#     "Supplier": {
#         "autoname": "entropy.utils.custom_naming.CustomSupplier.autoname",
#         "validate": "entropy.utils.custom_naming.CustomSupplier.validate"
#     }
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"entropy.tasks.all"
# 	],
# 	"daily": [
# 		"entropy.tasks.daily"
# 	],
# 	"hourly": [
# 		"entropy.tasks.hourly"
# 	],
# 	"weekly": [
# 		"entropy.tasks.weekly"
# 	],
# 	"monthly": [
# 		"entropy.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "entropy.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "entropy.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "entropy.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["entropy.utils.before_request"]
# after_request = ["entropy.utils.after_request"]

# Job Events
# ----------
# before_job = ["entropy.utils.before_job"]
# after_job = ["entropy.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"entropy.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

