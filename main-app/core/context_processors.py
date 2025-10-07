from .models import MaintenanceBanner

def maintenance_banner(request):
    banner = MaintenanceBanner.get_active()
    return {"maintenance_banner": banner}
