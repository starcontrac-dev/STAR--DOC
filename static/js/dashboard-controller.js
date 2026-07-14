/**
 * dashboard-controller.js
 * Lógica JavaScript para el Dashboard de STAR-DOC.
 * Administra la obtención de métricas, renderizado de gráficos con Chart.js
 * y el estado de la infraestructura Web3 IPFS/IPNS.
 */

document.addEventListener("DOMContentLoaded", function () {
    console.log("Dashboard loaded, fetching data...");
    fetchDashboardData();
});

async function fetchDashboardData() {
    try {
        const token = localStorage.getItem("access_token");
        if (!token) {
            console.warn("No access token found, redirecting to login.");
            window.location.href = '/login';
            return;
        }

        const response = await fetch('/dashboard/data', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        if (response.ok) {
            const data = await response.json();
            console.log("Dashboard data received:", data);
            updateDashboardUI(data);

            // Si es admin, cargar métricas completas desde /api/metricas/dashboard-completo
            if (data.is_admin) {
                fetchFullMetrics(token);
                
                // Mostrar sección IPFS y cargar paneles de infraestructura
                const adminIpfsSec = document.getElementById("admin-ipfs-section");
                if (adminIpfsSec) adminIpfsSec.classList.remove("hidden");
                initIPFS(token);
            }
        } else {
            console.error("Dashboard API Error:", response.status);
            if (response.status === 401) {
                window.location.href = '/login';
            }
        }
    } catch (error) {
        console.error("Fetch error:", error);
    }
}

async function fetchFullMetrics(token) {
    try {
        const resp = await fetch('/api/metricas/dashboard-completo', {
            headers: { 'Authorization': 'Bearer ' + token }
        });
        if (resp.ok) {
            const metrics = await resp.json();
            console.log("Full metrics received:", metrics);
            updateFullMetricsUI(metrics);
        }
    } catch (e) {
        console.error("Error fetching full metrics:", e);
    }
}

function updateDashboardUI(data) {
    // Public Stats Strings
    if (document.getElementById('stat-docs')) document.getElementById('stat-docs').textContent = data.document_activity || 0;
    if (document.getElementById('stat-templates')) document.getElementById('stat-templates').textContent = data.total_templates || 0;

    // Time saved logic
    if (document.getElementById('stat-time')) {
        const timeVal = (data.document_activity || 0) * 20;
        const timeDisplay = timeVal > 60 ? (timeVal / 60).toFixed(1) + " Horas" : timeVal + " Min";
        document.getElementById('stat-time').textContent = timeDisplay;
    }

    // --- Appointments (Citas) para Todos ---
    if (data.appointments) {
        const apptSection = document.getElementById('appointments-section');
        if (apptSection) apptSection.classList.remove('hidden');

        const ap = data.appointments;

        // Modificar los encabezados de texto si es un usuario común
        const divider = document.querySelector('#appointments-section .divider');
        if (divider) {
            divider.textContent = data.is_admin ? '📅 AGENDA DE CITAS' : '📅 REUNIONES PROGRAMADAS';
        }
        
        const cardTitle = document.querySelector('#appt-table-col .card-title');
        if (cardTitle) {
            if (data.is_admin) {
                cardTitle.innerHTML = `<i class="bi bi-calendar3 text-blue-400"></i> Próximas Citas Programadas <span class="badge badge-sm badge-primary ml-auto" id="appointments-badge">${ap.total}</span>`;
            } else {
                cardTitle.innerHTML = `<i class="bi bi-calendar3 text-blue-400"></i> Reuniones Programadas <span class="badge badge-sm badge-primary ml-auto" id="appointments-badge">${ap.total}</span>`;
            }
        }

        if (document.getElementById('stat-appointments-total')) document.getElementById('stat-appointments-total').textContent = ap.total;
        if (document.getElementById('stat-appointments-pending')) document.getElementById('stat-appointments-pending').textContent = ap.pending;
        if (document.getElementById('stat-appointments-confirmed')) document.getElementById('stat-appointments-confirmed').textContent = ap.confirmed;
        if (document.getElementById('appointments-badge')) document.getElementById('appointments-badge').textContent = ap.total;

        // Actualizar la insignia de la app PWA con el total de citas pendientes
        if (typeof window.updatePwaBadge === 'function') {
            window.updatePwaBadge(ap.pending);
        }

        // Si el usuario no es admin, optimizamos el ancho al 100%, ocultamos los KPIs y la columna de leads
        if (!data.is_admin) {
            const kpis = document.getElementById('appointments-kpis');
            if (kpis) kpis.classList.add('hidden');

            const leadsCol = document.getElementById('leads-sidebar-col');
            if (leadsCol) leadsCol.classList.add('hidden');

            const apptCol = document.getElementById('appt-table-col');
            if (apptCol) {
                apptCol.classList.remove('lg:col-span-2');
                apptCol.classList.add('lg:col-span-3');
            }
        }

        renderAppointmentsList(ap.list || [], data.is_admin);
    }

    // Admin Stats
    if (data.is_admin) {
        const adminRow = document.getElementById('admin-stats-row');
        const adminCharts = document.getElementById('admin-charts-row');
        if (adminRow) adminRow.classList.remove('hidden');
        if (adminCharts) adminCharts.classList.remove('hidden');

        if (document.getElementById('stat-users')) document.getElementById('stat-users').textContent = data.total_users;
        if (document.getElementById('stat-disk') && data.system_health) document.getElementById('stat-disk').textContent = data.system_health.disk_usage;

        if (data.storage_distribution) renderStorageChart(data.storage_distribution);
        
        // AI Metrics (FASE 8)
        if (data.ai_metrics) {
            updateAIMetricsUI(data.ai_metrics);
        }

        // --- Bandejas de Aprobaciones Pendientes (Contratos y Plantillas) ---
        const docsList = document.getElementById('pending-docs-list');
        const docsCountBadge = document.getElementById('pending-docs-count');
        const pDocs = data.pending_documents_to_review || [];
        
        if (docsCountBadge) docsCountBadge.textContent = pDocs.length;
        if (docsList) {
            if (pDocs.length === 0) {
                docsList.innerHTML = '<p class="text-gray-500 text-xs py-4 text-center">No hay contratos pendientes de revisión.</p>';
            } else {
                docsList.innerHTML = pDocs.map(d => `
                    <div class="flex items-center justify-between p-3 rounded-lg border border-white/5 bg-white/[0.01] hover:bg-white/[0.03] transition-colors">
                        <div class="min-w-0 flex-1">
                            <p class="text-xs font-semibold text-gray-200 truncate" title="${d.filename}">${d.filename}</p>
                            <p class="text-[10px] text-gray-500 mt-0.5 truncate" title="${d.preview || ''}">${d.preview ? d.preview.substring(0, 80) + '...' : 'Sin contenido'}</p>
                            <div class="flex items-center gap-2 mt-1">
                                <span class="text-[10px] text-gray-600"><i class="bi bi-person"></i> ${d.author_name || 'Desconocido'}</span>
                                <span class="text-[10px] text-gray-600"><i class="bi bi-calendar3"></i> ${new Date(d.upload_date).toLocaleDateString('es-CO')}</span>
                            </div>
                        </div>
                        <div class="flex gap-1.5 ml-3 shrink-0">
                            <button class="btn btn-xs btn-outline btn-info text-white gap-0.5" onclick="viewDocFromDashboard(${d.id})" title="Ver documento completo">
                                <i class="bi bi-eye"></i> Ver
                            </button>
                            <button class="btn btn-xs btn-success text-white" onclick="quickApproveDoc(${d.id})" title="Aprobar rápido">
                                <i class="bi bi-check-lg"></i>
                            </button>
                            <button class="btn btn-xs btn-error text-white" onclick="viewDocFromDashboard(${d.id}, true)" title="Rechazar (requiere comentarios)">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        </div>
                    </div>
                `).join('');
            }
        }

        const templatesList = document.getElementById('pending-templates-list');
        const templatesCountBadge = document.getElementById('pending-templates-count');
        const pTemplates = data.pending_templates_to_review || [];
        
        if (templatesCountBadge) templatesCountBadge.textContent = pTemplates.length;
        if (templatesList) {
            if (pTemplates.length === 0) {
                templatesList.innerHTML = '<p class="text-gray-500 text-xs py-4 text-center">No hay plantillas pendientes de revisión.</p>';
            } else {
                templatesList.innerHTML = pTemplates.map(t => `
                    <div class="flex items-center justify-between p-3 rounded-lg border border-white/5 bg-white/[0.01] hover:bg-white/[0.03] transition-colors">
                        <div class="min-w-0 flex-1">
                            <p class="text-xs font-semibold text-gray-200 truncate" title="${t.filename}">${t.filename}</p>
                            <p class="text-[10px] text-gray-500 font-mono">${t.description || 'Sin descripción'}</p>
                        </div>
                        <div class="flex gap-2 ml-3">
                            <button class="btn btn-xs btn-success text-white" onclick="approveTemplateFromDashboard(${t.id})">Aprobar</button>
                            <button class="btn btn-xs btn-error text-white" onclick="rejectTemplateFromDashboard(${t.id})">Rechazar</button>
                        </div>
                    </div>
                `).join('');
            }
        }
    }

    // Public Charts
    if (data.activity_history) renderActivityChart(data.activity_history);
    if (data.template_usage) renderTemplateChart(data.template_usage);
    if (data.hourly_activity) renderHourlyChart(data.hourly_activity);
}

function updateFullMetricsUI(m) {
    // --- Sistema ---
    if (m.sistema) {
        const s = m.sistema;
        if (document.getElementById('stat-cpu')) document.getElementById('stat-cpu').textContent = s.cpu_percent + '%';
        if (document.getElementById('stat-ram')) document.getElementById('stat-ram').textContent = s.ram_percent + '%';
        if (document.getElementById('stat-uptime')) document.getElementById('stat-uptime').textContent = s.uptime;
        if (document.getElementById('stat-disk')) document.getElementById('stat-disk').textContent = s.disk_percent + '%';
    }

    // --- Usuarios ---
    if (m.usuarios) {
        if (document.getElementById('stat-users')) document.getElementById('stat-users').textContent = m.usuarios.total;
    }

    // --- Tools ---
    if (m.tools) {
        if (document.getElementById('stat-tool-calls')) document.getElementById('stat-tool-calls').textContent = m.tools.total_calls;

        // Gráfico de ranking de herramientas
        if (m.tools.ranking && m.tools.ranking.length > 0) {
            renderToolsRankingChart(m.tools.ranking);
        }
    }

    // --- Skills ---
    if (m.skills) {
        if (document.getElementById('skills-count')) document.getElementById('skills-count').textContent = m.skills.total_disponibles;
        renderSkillsList(m.skills);
    }

    // --- Log de actividad reciente de tools ---
    if (m.tools && m.tools.ranking) {
        renderRecentToolsLog(m.tools.by_tool);
    }

    // --- Leads ---
    if (m.leads) {
        if (document.getElementById('stat-leads-total')) document.getElementById('stat-leads-total').textContent = m.leads.total;
        renderLeadsList(m.leads.list || []);
    }
}

// --- Helpers de formato para citas ---
function getStatusBadge(status) {
    const map = {
        'pending':    { label: 'Pendiente',    class: 'badge-warning' },
        'confirmed':  { label: 'Confirmada',   class: 'badge-success' },
        'completed':  { label: 'Completada',   class: 'badge-info' },
        'cancelled':  { label: 'Cancelada',    class: 'badge-error' },
        'rescheduled':{ label: 'Reprogramada',  class: 'badge-primary' },
        'no_show':    { label: 'No asistió',   class: 'badge-ghost' }
    };
    const s = map[status] || { label: status, class: 'badge-neutral' };
    return `<span class="badge badge-sm ${s.class}">${s.label}</span>`;
}

function getTypeIcon(type) {
    const map = {
        'video_call':  '<i class="bi bi-camera-video text-blue-400"></i>',
        'videocall':   '<i class="bi bi-camera-video text-blue-400"></i>',
        'phone_call':  '<i class="bi bi-telephone text-green-400"></i>',
        'in_person':   '<i class="bi bi-building text-amber-400"></i>',
        'whatsapp':    '<i class="bi bi-whatsapp text-emerald-400"></i>'
    };
    return map[type] || '<i class="bi bi-calendar text-gray-400"></i>';
}

function formatDateNice(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
    const dateOnly = new Date(d); dateOnly.setHours(0, 0, 0, 0);

    const options = { weekday: 'short', day: 'numeric', month: 'short' };
    const formatted = d.toLocaleDateString('es-CO', options);

    if (dateOnly.getTime() === today.getTime()) return `<span class="text-green-400 font-bold">Hoy</span> · ${formatted}`;
    if (dateOnly.getTime() === tomorrow.getTime()) return `<span class="text-amber-400 font-bold">Mañana</span> · ${formatted}`;
    if (dateOnly < today) return `<span class="text-red-400">Pasada</span> · ${formatted}`;
    return formatted;
}

function renderAppointmentsList(appointments, isAdmin) {
    const container = document.getElementById('appointments-list');
    if (!container) return;

    // Filtrar automáticamente las citas pasadas en tiempo real (según fecha, hora e instante de finalización)
    const now = new Date();

    const activeAppointments = appointments.filter(a => {
        // Excluir citas canceladas, completadas o no presentadas del panel de control
        if (a.status === 'cancelled' || a.status === 'completed' || a.status === 'no_show') {
            return false;
        }
        
        // Calcular el instante exacto de inicio y fin de la reunión
        const startDt = new Date(`${a.date}T${a.time}:00`);
        const durationMinutes = parseInt(a.duration) || 30;
        const endDt = new Date(startDt.getTime() + durationMinutes * 60 * 1000);

        // Si el instante actual es mayor que la hora de finalización, la cita ya ha expirado
        return endDt.getTime() > now.getTime();
    });

    if (activeAppointments.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8">
                <i class="bi bi-calendar-x text-4xl text-gray-600"></i>
                <p class="text-gray-500 mt-2">No hay próximas citas programadas</p>
            </div>`;
        return;
    }

    container.innerHTML = activeAppointments.map(a => {
        // Generar nombre de la sala de Jitsi
        const roomName = a.jitsi_room_name || (a.meeting_link ? a.meeting_link.split('/').pop() : 'sala-vacia');
        const localMeetUrl = `${window.location.origin}/dashboard/reunion/${roomName}`;

        if (!isAdmin) {
            // Estructura simplificada exigida por el usuario para no administradores
            const dateNice = formatDateNice(a.date);
            const statusLabel = a.status === 'confirmed' ? 'Confirmada' : (a.status === 'pending' ? 'Pendiente' : a.status);
            const statusBadgeClass = a.status === 'confirmed' ? 'badge-success' : 'badge-warning';

            return `
            <div class="p-4 rounded-xl bg-gradient-to-r from-white/5 to-white/[0.02] border border-white/10 hover:border-white/20 transition-all duration-300 group">
                <div class="flex flex-col gap-2">
                    <div class="flex items-center justify-between">
                        <span class="text-white font-medium text-sm">Reunión de ${a.lead_name}</span>
                        <span class="badge badge-sm ${statusBadgeClass}">${statusLabel}</span>
                    </div>
                    <p class="text-gray-400 text-xs">${a.reason}</p>
                    <div class="text-[11px] text-gray-500 flex flex-wrap gap-1 items-center">
                        <span>${dateNice} · ${a.time} · ${a.duration} min</span>
                    </div>
                    <div class="mt-2 text-xs flex justify-between items-center gap-2">
                        <a href="${localMeetUrl}" target="_blank" class="text-indigo-400 hover:text-indigo-300 font-mono flex items-center gap-1 break-all">
                            <i class="bi bi-camera-video-fill"></i> ${localMeetUrl}
                        </a>
                        <button onclick="markAppointmentCompleted(${a.id})" class="btn btn-xs btn-ghost text-emerald-400 hover:text-emerald-300 gap-1 p-1 h-auto min-h-0">
                            <i class="bi bi-check-lg"></i> Completar
                        </button>
                    </div>
                </div>
            </div>`;
        }

        // Renderizado para administrador (con botones de reprogramar, etc.)
        let meetBtn = '';
        if (a.meeting_link && a.meeting_link.startsWith('http')) {
            const isGoogleMeet = a.meeting_link.includes('meet.google.com');
            const isJitsi = a.meeting_link.includes('meet.jit.si');
            
            if (isJitsi) {
                const parts = a.meeting_link.split('/');
                const rName = parts[parts.length - 1] || a.jitsi_room_name;
                const target = (window.isPwaStandalone && window.isPwaStandalone()) ? '_self' : '_blank';
                meetBtn = `<a href="/dashboard/reunion/${rName}" target="${target}" class="btn btn-xs bg-indigo-600 hover:bg-indigo-500 text-white border-none gap-1 shadow-md shadow-indigo-600/20"><i class="bi bi-camera-video-fill"></i> Sala Jitsi</a>`;
            } else {
                const btnClass = isGoogleMeet ? 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-cyan-600/20 border-none' : 'btn-outline btn-info';
                const btnLabel = isGoogleMeet ? 'Google Meet' : 'Meet';
                meetBtn = `<a href="${a.meeting_link}" target="_blank" class="btn btn-xs ${btnClass} gap-1 shadow-md"><i class="bi bi-camera-video-fill"></i> ${btnLabel}</a>`;
            }
        } else if (a.jitsi_room_name) {
            const target = (window.isPwaStandalone && window.isPwaStandalone()) ? '_self' : '_blank';
            meetBtn = `<a href="/dashboard/reunion/${a.jitsi_room_name}" target="${target}" class="btn btn-xs bg-indigo-600 hover:bg-indigo-500 text-white border-none gap-1 shadow-md shadow-indigo-600/20"><i class="bi bi-camera-video-fill"></i> Sala Jitsi</a>`;
        }

        return `
        <div class="p-4 rounded-xl bg-gradient-to-r from-white/5 to-white/[0.02] border border-white/10 hover:border-white/20 transition-all duration-300 group">
            <div class="flex items-start gap-3">
                <!-- Icono de tipo -->
                <div class="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center text-lg shrink-0 group-hover:bg-white/15 transition-colors">
                    ${getTypeIcon(a.type)}
                </div>
                <!-- Contenido -->
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-white font-medium text-sm truncate">${a.lead_name}</span>
                        ${getStatusBadge(a.status)}
                    </div>
                    <p class="text-gray-400 text-xs truncate mb-2">${a.reason}</p>
                    <div class="flex flex-wrap items-center gap-3 text-[11px]">
                        <span class="text-cyan-400 flex items-center gap-1">
                            <i class="bi bi-calendar3"></i> ${formatDateNice(a.date)}
                        </span>
                        <span class="text-purple-400 flex items-center gap-1">
                            <i class="bi bi-clock"></i> ${a.time} · ${a.duration} min
                        </span>
                        <span class="text-gray-500 flex items-center gap-1">
                            <i class="bi bi-envelope"></i> ${a.lead_email}
                        </span>
                    </div>
                </div>
                <!-- Acciones -->
                <div class="shrink-0 flex flex-col items-end gap-1.5">
                    ${meetBtn}
                    <div class="flex gap-1 mt-1">
                        <!-- Reprogramar -->
                        <button onclick="openRescheduleModal(${a.id}, '${a.lead_name.replace(/'/g, "\\'")}', '${a.date}', '${a.time}')" 
                                class="btn btn-xs btn-outline btn-warning py-0.5 px-1.5 tooltip tooltip-left" 
                                data-tip="Reprogramar">
                            <i class="bi bi-pencil-square"></i>
                        </button>
                        <!-- Cancelar -->
                        <button onclick="cancelAppointment(${a.id}, '${a.lead_name.replace(/'/g, "\\'")}')" 
                                class="btn btn-xs btn-outline btn-error py-0.5 px-1.5 tooltip tooltip-left" 
                                data-tip="Cancelar">
                            <i class="bi bi-calendar-x"></i>
                        </button>
                        <!-- Marcar como completada -->
                        <button onclick="markAppointmentCompleted(${a.id})" 
                                class="btn btn-xs btn-outline btn-success py-0.5 px-1.5 tooltip tooltip-left" 
                                data-tip="Completar">
                            <i class="bi bi-check-lg"></i>
                        </button>
                    </div>
                    <span class="text-[9px] text-gray-600 mt-1">${a.created_by === 'ai_agent' ? '🤖 IA' : '👤 Manual'}</span>
                </div>
            </div>
            ${a.notes ? `<div class="mt-2 pl-13 text-[10px] text-gray-600 italic border-t border-white/5 pt-2">📝 ${a.notes.substring(0, 150)}${a.notes.length > 150 ? '...' : ''}</div>` : ''}
        </div>`;
    }).join('');
}

function renderLeadsList(leads) {
    const container = document.getElementById('leads-list');
    if (!container) return;

    if (leads.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-xs text-center py-4">No hay leads registrados</p>';
        return;
    }

    const statusColors = {
        'new': 'bg-blue-500', 'contacted': 'bg-cyan-500', 'qualified': 'bg-amber-500',
        'appointed': 'bg-green-500', 'converted': 'bg-emerald-500', 'discarded': 'bg-gray-600'
    };
    const statusLabels = {
        'new': 'Nuevo', 'contacted': 'Contactado', 'qualified': 'Calificado',
        'appointed': 'Con Cita', 'converted': 'Convertido', 'discarded': 'Descartado'
    };

    container.innerHTML = leads.map(l => `
        <div class="p-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 transition-colors">
            <div class="flex items-center gap-2 mb-1">
                <span class="w-2 h-2 rounded-full ${statusColors[l.status] || 'bg-gray-500'}"></span>
                <span class="text-white text-xs font-medium">${l.name}</span>
                <span class="badge badge-xs badge-ghost ml-auto">${statusLabels[l.status] || l.status}</span>
            </div>
            <p class="text-gray-500 text-[10px] ml-4">${l.email}</p>
            ${l.service_interest ? `<p class="text-gray-600 text-[10px] ml-4 mt-0.5 italic">${l.service_interest}</p>` : ''}
            ${l.phone ? `<p class="text-gray-600 text-[10px] ml-4 flex items-center gap-1"><i class="bi bi-telephone"></i> ${l.phone}</p>` : ''}
        </div>
    `).join('');
}

function renderSkillsList(skillsData) {
    const container = document.getElementById('skills-list');
    if (!container) return;

    const nombres = skillsData.nombres || [];
    const usage = skillsData.usage || {};

    if (nombres.length === 0) {
        container.innerHTML = '<p class="text-gray-500 text-xs">No hay skills cargados</p>';
        return;
    }

    container.innerHTML = nombres.map(name => {
        const u = usage[name];
        const activations = u ? u.activations : 0;
        const lastUsed = u ? u.last_used : 'Nunca';
        const color = activations > 0 ? 'text-green-400' : 'text-gray-500';
        return `
            <div class="flex items-center justify-between p-2 rounded bg-white/5 hover:bg-white/10 transition-colors">
                <div class="flex items-center gap-2">
                    <span class="w-1.5 h-1.5 rounded-full ${activations > 0 ? 'bg-green-500' : 'bg-gray-600'}"></span>
                    <span class="text-xs text-gray-300 font-mono">${name}</span>
                </div>
                <div class="text-right">
                    <span class="text-[10px] ${color}">${activations} usos</span>
                    <br><span class="text-[9px] text-gray-600">${lastUsed}</span>
                </div>
            </div>
        `;
    }).join('');
}

function renderRecentToolsLog(byTool) {
    const container = document.getElementById('recent-tools-log');
    if (!container || !byTool) return;

    const entries = Object.entries(byTool);
    if (entries.length === 0) {
        container.innerHTML = '<p class="text-gray-500">Sin actividad todavía...</p>';
        return;
    }

    container.innerHTML = entries.map(([name, stats]) => {
        const statusIcon = stats.success_rate > 90 ? '🟢' : (stats.success_rate > 50 ? '🟡' : '🔴');
        return `
            <div class="flex items-center gap-2 text-gray-400 p-1 rounded hover:bg-white/5">
                <span>${statusIcon}</span>
                <span class="text-cyan-400">${name}</span>
                <span class="ml-auto text-gray-600">${stats.calls}x</span>
                <span class="text-purple-400">${stats.avg_ms}ms</span>
                <span class="${stats.success_rate > 90 ? 'text-green-400' : 'text-yellow-400'}">${stats.success_rate}%</span>
            </div>
        `;
    }).join('');
}

let toolsChartInstance = null;
function renderToolsRankingChart(ranking) {
    const ctx = document.getElementById('toolsRankingChart');
    if (!ctx) return;

    if (toolsChartInstance) toolsChartInstance.destroy();

    const topTools = ranking.slice(0, 8);
    const colors = [
        'rgba(236, 72, 153, 0.7)', 'rgba(167, 139, 250, 0.7)', 'rgba(59, 130, 246, 0.7)',
        'rgba(16, 185, 129, 0.7)', 'rgba(245, 158, 11, 0.7)', 'rgba(239, 68, 68, 0.7)',
        'rgba(6, 182, 212, 0.7)', 'rgba(139, 92, 246, 0.7)'
    ];

    toolsChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: topTools.map(t => t.name.replace(/_/g, ' ').substring(0, 20)),
            datasets: [{
                label: 'Ejecuciones',
                data: topTools.map(t => t.calls),
                backgroundColor: colors,
                borderColor: 'rgba(255,255,255,0.1)',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                y: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 9 } } }
            }
        }
    });
}

function renderActivityChart(history) {
    const ctx = document.getElementById('docsChart');
    if (!ctx) return;

    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.labels || [],
            datasets: [{
                label: 'Documentos',
                data: history.data || [],
                fill: true,
                backgroundColor: gradient,
                borderColor: '#3b82f6',
                tension: 0.4,
                borderWidth: 2,
                pointBackgroundColor: '#fff',
                pointBorderColor: '#3b82f6'
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 7 } }
            }
        }
    });
}

function renderTemplateChart(usageData) {
    const ctx = document.getElementById('templateChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(usageData),
            datasets: [{
                label: 'Uso',
                data: Object.values(usageData),
                backgroundColor: [
                    'rgba(59, 130, 246, 0.7)', 'rgba(16, 185, 129, 0.7)',
                    'rgba(245, 158, 11, 0.7)', 'rgba(239, 68, 68, 0.7)', 'rgba(139, 92, 246, 0.7)'
                ],
                borderColor: 'rgba(255, 255, 255, 0.1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

function renderHourlyChart(hourlyData) {
    const ctx = document.getElementById('hourlyChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Array.from({ length: 24 }, (_, i) => i + ':00'),
            datasets: [{
                label: 'Generaciones',
                data: hourlyData,
                backgroundColor: 'rgba(236, 72, 153, 0.7)', // Pink
                borderColor: 'rgba(236, 72, 153, 1)',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 12 } }
            }
        }
    });
}

function renderStorageChart(storageData) {
    const ctx = document.getElementById('storageChart');
    if (!ctx) return;

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Documentos (MB)', 'Plantillas (MB)'],
            datasets: [{
                data: [storageData.docs_mb, storageData.templates_mb],
                backgroundColor: ['#3b82f6', '#10b981'],
                borderColor: 'rgba(0,0,0,0)',
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#cbd5e1' } }
            }
        }
    });
}

// --- AI METRICS HELPERS (FASE 8) ---

function updateAIMetricsUI(ai) {
    if (document.getElementById('stat-ai-cost')) document.getElementById('stat-ai-cost').textContent = '$' + ai.estimated_cost_usd.toFixed(4);
    if (document.getElementById('stat-ai-tokens')) document.getElementById('stat-ai-tokens').textContent = ai.total_tokens_estimated.toLocaleString();
    if (document.getElementById('stat-ai-latency')) document.getElementById('stat-ai-latency').textContent = ai.avg_latency_ms.toFixed(0) + 'ms';
    if (document.getElementById('stat-ai-success')) document.getElementById('stat-ai-success').textContent = ai.global_success_rate + '%';

    // Render AI Model Status Badges
    const container = document.getElementById('ai-models-status');
    if (container && ai.models) {
        container.innerHTML = '';
        Object.entries(ai.models).forEach(([model, stats]) => {
            const color = stats.circuit_breaker_state === 'closed' ? 'success' : (stats.circuit_breaker_state === 'open' ? 'error' : 'warning');
            const badge = `
                <div class="flex flex-col p-2 bg-white/5 rounded border border-white/5 min-w-[120px]">
                    <span class="text-[9px] text-gray-500 uppercase font-mono">${model}</span>
                    <div class="flex items-center gap-2">
                         <span class="w-1.5 h-1.5 rounded-full bg-${color === 'success' ? 'green' : (color === 'error' ? 'red' : 'yellow')}-500"></span>
                         <span class="text-xs font-bold text-gray-300 capitalize">${stats.circuit_breaker_state}</span>
                    </div>
                </div>
            `;
            container.innerHTML += badge;
        });
    }

    // Render AI Performance Chart
    renderAIModelChart(ai.models);
}

let aiChartInstance = null;
function renderAIModelChart(models) {
    const ctx = document.getElementById('aiModelChart');
    if (!ctx) return;

    if (aiChartInstance) aiChartInstance.destroy();

    const labels = Object.keys(models);
    const latencies = labels.map(l => models[l].avg_latency_ms);
    const successRates = labels.map(l => models[l].success_rate_percent);

    aiChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Latencia Promedio (ms)',
                    data: latencies,
                    backgroundColor: 'rgba(167, 139, 250, 0.7)',
                    borderColor: '#a78bfa',
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: 'Tasa de Éxito (%)',
                    data: successRates,
                    backgroundColor: 'rgba(59, 130, 246, 0.2)',
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    type: 'line',
                    tension: 0.4,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#94a3b8', font: { size: 10 } } } },
            scales: {
                y: { 
                    beginAtZero: true, 
                    title: { display: true, text: 'Latencia (ms)', color: '#94a3b8' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                y1: { 
                    beginAtZero: true,
                    max: 100,
                    position: 'right',
                    title: { display: true, text: 'Éxito (%)', color: '#94a3b8' },
                    grid: { display: false },
                    ticks: { color: '#94a3b8' }
                },
                x: { ticks: { color: '#94a3b8', font: { size: 9 } } }
            }
        }
    });
}

// --- INTEGRACIÓN IPFS & IPNS (WEB3) ---

function initIPFS(token) {
    console.log("Inicializando paneles IPFS/IPNS/Webhooks para Administrador...");
    
    // Listeners de Formularios de IPNS
    const createKeyForm = document.getElementById("create-ipns-key-form");
    if (createKeyForm) {
        createKeyForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const keyNameInput = document.getElementById("ipns-key-name-input");
            const submitBtn = document.getElementById("create-key-btn");
            if (!keyNameInput || !submitBtn) return;

            const keyName = keyNameInput.value.trim();
            if (!keyName) return;

            try {
                submitBtn.disabled = true;
                submitBtn.innerHTML = `<span class="loading loading-spinner loading-xs"></span> Creando...`;

                const response = await fetch(`/ipfs/ipns/key?key_name=${encodeURIComponent(keyName)}`, {
                    method: "POST",
                    headers: {
                        "Authorization": "Bearer " + token
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    window.showToast(`Clave IPNS '${data.key_name}' creada exitosamente.`, "success");
                    keyNameInput.value = "";
                    await fetchIPNSKeys(token);
                } else {
                    const err = await response.json();
                    window.showToast("Error al crear clave: " + (err.detail || "Desconocido"), "danger");
                }
            } catch (error) {
                console.error("Error:", error);
                window.showToast("Error de conexión al crear clave.", "danger");
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<i class="bi bi-plus-lg"></i> Crear Clave`;
            }
        });
    }

    const publishForm = document.getElementById("publish-ipns-form");
    if (publishForm) {
        publishForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const keySelect = document.getElementById("ipns-key-select");
            const cidInput = document.getElementById("ipns-cid-input");
            const submitBtn = document.getElementById("publish-ipns-btn");
            if (!keySelect || !cidInput || !submitBtn) return;

            const keyName = keySelect.value;
            const cid = cidInput.value.trim();

            if (!keyName || !cid) {
                window.showToast("Por favor complete todos los campos.", "danger");
                return;
            }

            try {
                submitBtn.disabled = true;
                submitBtn.innerHTML = `<span class="loading loading-spinner loading-xs"></span> Publicando...`;

                const response = await fetch(`/ipfs/ipns/publish?key_name=${encodeURIComponent(keyName)}&cid=${encodeURIComponent(cid)}`, {
                    method: "POST",
                    headers: {
                        "Authorization": "Bearer " + token
                    }
                });

                if (response.ok) {
                    const data = await response.json();
                    window.showToast("Publicado en IPNS mutable exitosamente.", "success");
                    cidInput.value = "";
                } else {
                    const err = await response.json();
                    window.showToast("Error al publicar en IPNS: " + (err.detail || "Desconocido"), "danger");
                }
            } catch (error) {
                console.error("Error:", error);
                window.showToast("Error de conexión al publicar en IPNS.", "danger");
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<i class="bi bi-cloud-arrow-up"></i> Publicar Versión`;
            }
        });
    }

    // Listener de Formulario de Webhooks
    const createWebhookForm = document.getElementById("create-webhook-form");
    if (createWebhookForm) {
        createWebhookForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            const nameInput = document.getElementById("webhook-name");
            const urlInput = document.getElementById("webhook-url");
            const submitBtn = createWebhookForm.querySelector("button[type='submit']");
            if (!urlInput || !submitBtn) return;

            const name = nameInput ? nameInput.value.trim() : "";
            const url = urlInput.value.trim();

            // Capturar eventos seleccionados
            const eventCheckboxes = createWebhookForm.querySelectorAll("input[name='webhook-events']:checked");
            const events = Array.from(eventCheckboxes).map(cb => cb.value);

            if (events.length === 0) {
                window.showToast("Debe seleccionar al menos un evento para el webhook.", "danger");
                return;
            }

            try {
                submitBtn.disabled = true;
                submitBtn.innerHTML = `<span class="loading loading-spinner loading-xs"></span> Registrando...`;

                const response = await fetch("/ipfs/webhooks", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": "Bearer " + token
                    },
                    body: JSON.stringify({
                        name: name || null,
                        url: url,
                        events: events
                    })
                });

                if (response.ok) {
                    window.showToast("Webhook registrado correctamente.", "success");
                    if (nameInput) nameInput.value = "";
                    urlInput.value = "";
                    await fetchWebhooks(token);
                } else {
                    const err = await response.json();
                    window.showToast("Error al registrar Webhook: " + (err.detail || "Desconocido"), "danger");
                }
            } catch (error) {
                console.error("Error al registrar Webhook:", error);
                window.showToast("Error de conexión al registrar Webhook.", "danger");
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<i class="bi bi-plus-circle"></i> Registrar Webhook`;
            }
        });
    }

    // Registrar funciones globales en window
    window.runGarbageCollection = async function() {
        const gcBtn = document.getElementById("gc-btn");
        if (!gcBtn) return;

        try {
            gcBtn.disabled = true;
            gcBtn.innerHTML = `<span class="loading loading-spinner loading-xs"></span> Limpiando nodo...`;

            const response = await fetch("/ipfs/gc", {
                method: "POST",
                headers: {
                    "Authorization": "Bearer " + token
                }
            });

            if (response.ok) {
                const resData = await response.json();
                console.log("GC completado:", resData);
                window.showToast("Garbage Collection ejecutado con éxito en el nodo Kubo.", "success");
                await fetchIPFSStatus(token);
            } else {
                const err = await response.json();
                window.showToast("Error al ejecutar GC: " + (err.detail || "Desconocido"), "danger");
            }
        } catch (error) {
            console.error("Error GC:", error);
            window.showToast("Error de conexión al ejecutar GC.", "danger");
        } finally {
            gcBtn.disabled = false;
            gcBtn.innerHTML = `🧹 Ejecutar Garbage Collection`;
        }
    };

    window.deleteWebhook = async function(id) {
        if (!confirm("¿Está seguro de que desea eliminar este Webhook?")) return;

        try {
            const response = await fetch(`/ipfs/webhooks/${id}`, {
                method: "DELETE",
                headers: {
                    "Authorization": "Bearer " + token
                }
            });

            if (response.ok) {
                window.showToast("Webhook eliminado exitosamente.", "success");
                await fetchWebhooks(token);
            } else {
                const err = await response.json();
                window.showToast("Error al eliminar Webhook: " + (err.detail || "Desconocido"), "danger");
            }
        } catch (error) {
            console.error("Error al eliminar webhook:", error);
            window.showToast("Error de conexión al eliminar Webhook.", "danger");
        }
    };

    // Carga inicial de datos
    fetchIPFSStatus(token);
    fetchIPNSKeys(token);
    fetchWebhooks(token);

    // Auto refresco periódico
    setInterval(() => {
        fetchIPFSStatus(token);
        fetchWebhooks(token);
    }, 30000);
}

async function fetchIPFSStatus(token) {
    try {
        const response = await fetch('/ipfs/repo/stats', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        const statusVal = document.getElementById("ipfs-status-value");
        const storageVal = document.getElementById("ipfs-storage-value");
        const peersVal = document.getElementById("ipfs-peers-value");
        const peerIdVal = document.getElementById("ipfs-peer-id");
        const nodeFigure = document.getElementById("ipfs-node-figure");

        // Nuevos campos de mantenimiento en el dashboard
        const repoPathVal = document.getElementById("ipfs-repo-path");
        const repoObjectsVal = document.getElementById("ipfs-repo-objects");
        const nodeVersionVal = document.getElementById("ipfs-node-version");

        if (response.ok) {
            const data = await response.json();
            
            if (data.online) {
                if (statusVal) {
                    statusVal.className = "stat-value text-sm flex items-center gap-2 text-success mt-1";
                    statusVal.innerHTML = `<i class="bi bi-check-circle-fill"></i> Conectado`;
                }
                if (nodeFigure) {
                    nodeFigure.className = "stat-figure text-success";
                    nodeFigure.innerHTML = `<i class="bi bi-cpu text-3xl"></i>`;
                }
            } else {
                if (statusVal) {
                    statusVal.className = "stat-value text-sm flex items-center gap-2 text-error mt-1";
                    statusVal.innerHTML = `<i class="bi bi-x-circle-fill"></i> Desconectado`;
                }
                if (nodeFigure) {
                    nodeFigure.className = "stat-figure text-error";
                    nodeFigure.innerHTML = `<i class="bi bi-cpu text-3xl"></i>`;
                }
            }

            if (peersVal) {
                const peersCount = data.peers_connected !== undefined && data.peers_connected !== null ? data.peers_connected : 0;
                peersVal.textContent = peersCount.toLocaleString();
            }

            if (peerIdVal && data.peer_id) {
                peerIdVal.textContent = `Peer ID: ${data.peer_id}`;
                peerIdVal.title = data.peer_id;
            } else if (peerIdVal) {
                peerIdVal.textContent = `Peer ID: Desconocido`;
            }

            if (storageVal) {
                const sizeBytes = data.repo_size_bytes || 0;
                const maxBytes = data.repo_max_bytes || 0;
                const sizeMB = (sizeBytes / (1024 * 1024)).toFixed(2);
                const maxMB = (maxBytes / (1024 * 1024)).toFixed(0);
                if (maxBytes > 0) {
                    storageVal.textContent = `${sizeMB} MB / ${maxMB} MB`;
                } else {
                    storageVal.textContent = `${sizeMB} MB (Ilimitado)`;
                }
            }

            // Actualizar campos de mantenimiento
            if (repoPathVal) repoPathVal.textContent = data.repo_path || "Desconocida";
            if (repoObjectsVal) repoObjectsVal.textContent = (data.num_objects || 0).toLocaleString();
            if (nodeVersionVal) nodeVersionVal.textContent = data.version || "Desconocida";

        } else {
            if (statusVal) {
                statusVal.className = "stat-value text-sm flex items-center gap-2 text-error mt-1";
                statusVal.innerHTML = `<i class="bi bi-x-circle-fill"></i> Desconectado`;
            }
        }
    } catch (error) {
        console.error("Error al obtener stats de IPFS:", error);
        const statusVal = document.getElementById("ipfs-status-value");
        if (statusVal) {
            statusVal.className = "stat-value text-sm flex items-center gap-2 text-error mt-1";
            statusVal.innerHTML = `<i class="bi bi-x-circle-fill"></i> Error de Red`;
        }
    }
}

async function fetchIPNSKeys(token) {
    try {
        const response = await fetch('/ipfs/ipns/keys', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        const keysList = document.getElementById("ipns-keys-list");
        const keysCount = document.getElementById("ipns-keys-count");
        const keySelect = document.getElementById("ipns-key-select");

        if (response.ok) {
            const data = await response.json();
            let keys = [];
            if (data.Keys) {
                keys = data.Keys;
            } else if (Array.isArray(data)) {
                keys = data.map(k => ({
                    Name: k.key_name,
                    Id: k.ipns_id
                }));
            }

            if (keysCount) keysCount.textContent = keys.length;

            if (keySelect) {
                // Guardar valor actual
                const currentVal = keySelect.value;
                keySelect.innerHTML = `<option value="" disabled>Seleccione clave...</option>`;
                keys.forEach(k => {
                    keySelect.innerHTML += `<option value="${k.Name}">${k.Name} (${k.Id.substring(0, 8)}...)</option>`;
                });
                if (currentVal) {
                    keySelect.value = currentVal;
                } else if (keys.length > 0) {
                    const firstOption = keys.find(k => k.Name !== 'self') || keys[0];
                    if (firstOption) keySelect.value = firstOption.Name;
                }
            }

            if (keysList) {
                if (keys.length === 0) {
                    keysList.innerHTML = `
                        <tr>
                            <td colspan="3" class="text-center py-4 text-gray-500">
                                No hay claves IPNS generadas.
                            </td>
                        </tr>`;
                    return;
                }

                keysList.innerHTML = keys.map(k => {
                    const isSelf = k.Name === "self";
                    const nameBadge = isSelf ? `<span class="badge badge-xs badge-ghost">Por Defecto</span>` : "";
                    
                    return `
                        <tr class="hover:bg-white/5 border-b border-white/5 align-middle">
                            <td class="font-mono text-xs font-semibold py-3 text-cyan-300">
                                ${k.Name} ${nameBadge}
                            </td>
                            <td class="font-mono text-[10px] text-gray-400 max-w-[200px] truncate" title="${k.Id}">
                                ${k.Id}
                            </td>
                            <td class="text-right py-3 space-x-1 whitespace-nowrap">
                                <button onclick="copyToClipboard('${k.Id}', 'Dirección IPNS', this)" class="btn btn-ghost btn-xs text-info px-1 hover:bg-info/20" title="Copiar Dirección IPNS">
                                    <i class="bi bi-copy"></i>
                                </button>
                                <a href="https://ipfs.io/ipns/${k.Id}" target="_blank" class="btn btn-ghost btn-xs text-primary px-1 hover:bg-primary/20" title="Ver en Gateway Público">
                                    <i class="bi bi-box-arrow-up-right"></i>
                                </a>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        } else {
            if (keysList) {
                keysList.innerHTML = `
                    <tr>
                        <td colspan="3" class="text-center py-4 text-error">
                            Error al cargar claves IPNS (${response.status}).
                        </td>
                    </tr>`;
            }
        }
    } catch (error) {
        console.error("Error al obtener claves IPNS:", error);
        const keysList = document.getElementById("ipns-keys-list");
        if (keysList) {
            keysList.innerHTML = `
                <tr>
                    <td colspan="3" class="text-center py-4 text-error">
                        Error de red al cargar claves.
                    </td>
                </tr>`;
        }
    }
}

async function fetchWebhooks(token) {
    try {
        const response = await fetch('/ipfs/webhooks', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });

        const webhooksList = document.getElementById("webhooks-list");
        if (response.ok) {
            const data = await response.json();
            
            if (webhooksList) {
                if (!data || data.length === 0) {
                    webhooksList.innerHTML = `
                        <tr>
                            <td colspan="4" class="text-center py-4 text-gray-500 text-xs">
                                No hay Webhooks registrados.
                            </td>
                        </tr>`;
                    return;
                }

                webhooksList.innerHTML = data.map(w => {
                    const eventsBadge = w.events.map(ev => `<span class="badge badge-outline badge-xs border-warning/30 text-warning/70 mr-1">${ev}</span>`).join('');
                    return `
                        <tr class="hover:bg-white/5 border-b border-white/5 align-middle">
                            <td class="font-sans text-xs font-semibold py-3 text-white">
                                ${w.name || 'Sin Nombre'}
                            </td>
                            <td class="font-mono text-[10px] text-gray-400 max-w-[200px] truncate" title="${w.url}">
                                ${w.url}
                            </td>
                            <td class="py-3">
                                ${eventsBadge}
                            </td>
                            <td class="text-right py-3 space-x-1 whitespace-nowrap">
                                <button onclick="deleteWebhook(${w.id})" class="btn btn-ghost btn-xs text-error px-1 hover:bg-error/20" title="Eliminar Webhook">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        } else {
            if (webhooksList) {
                webhooksList.innerHTML = `
                    <tr>
                        <td colspan="4" class="text-center py-4 text-error text-xs">
                            Error al cargar Webhooks (${response.status}).
                        </td>
                    </tr>`;
            }
        }
    } catch (error) {
        console.error("Error al obtener Webhooks:", error);
        const webhooksList = document.getElementById("webhooks-list");
        if (webhooksList) {
            webhooksList.innerHTML = `
                <tr>
                    <td colspan="4" class="text-center py-4 text-error text-xs">
                        Error de red al cargar Webhooks.
                    </td>
                </tr>`;
        }
    }
}

// Función auxiliar global para copiar y mostrar toast
window.copyToClipboard = function(text, label = "Contenido", btnEl = null) {
    const copySuccess = () => {
        window.showToast(`${label} copiado al portapapeles.`, "success");
        if (btnEl) {
            const originalHTML = btnEl.innerHTML;
            btnEl.innerHTML = '<i class="bi bi-check-lg text-success scale-110 transition-transform"></i>';
            btnEl.classList.add('bg-success/10');
            setTimeout(() => {
                btnEl.innerHTML = originalHTML;
                btnEl.classList.remove('bg-success/10');
            }, 2000);
        }
    };

    if (!navigator.clipboard) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand("copy");
            copySuccess();
        } catch (err) {
            window.showToast("No se pudo copiar.", "danger");
        }
        document.body.removeChild(textArea);
        return;
    }
    navigator.clipboard.writeText(text).then(() => {
        copySuccess();
    }).catch(err => {
        console.error("Error al copiar:", err);
        window.showToast("Error al copiar al portapapeles.", "danger");
    });
}


// --- Lógica para Gestión de Citas (Editar/Cancelar/Reprogramar) ---

window.cancelAppointment = async function (id, name) {
    if (!confirm(`¿Estás seguro de que deseas cancelar la cita con ${name}?`)) return;

    try {
        const token = localStorage.getItem("access_token");
        const response = await fetch(`/api/appointments/${id}/status`, {
            method: 'PATCH',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: 'cancelled', cancellation_reason: 'Cancelado desde el panel de control' })
        });

        if (response.ok) {
            window.showToast("Cita cancelada correctamente. Se ha notificado al cliente.", "success");
            fetchDashboardData();
        } else {
            const errData = await response.json();
            window.showToast(errData.detail || "Error al cancelar la cita.", "error");
        }
    } catch (e) {
        console.error("Error al cancelar cita:", e);
        window.showToast("Error de conexión al cancelar la cita.", "error");
    }
};

window.markAppointmentCompleted = async function (id) {
    if (!confirm("¿Deseas marcar esta cita como completada?")) return;

    try {
        const token = localStorage.getItem("access_token");
        const response = await fetch(`/api/appointments/${id}/status`, {
            method: 'PATCH',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status: 'completed' })
        });

        if (response.ok) {
            window.showToast("Cita marcada como completada.", "success");
            fetchDashboardData();
        } else {
            const errData = await response.json();
            window.showToast(errData.detail || "Error al actualizar estado.", "error");
        }
    } catch (e) {
        console.error("Error:", e);
        window.showToast("Error de conexión.", "error");
    }
};

window.openRescheduleModal = function (id, name, date, time) {
    document.getElementById("reschedule-appointment-id").value = id;
    document.getElementById("reschedule-client-name").textContent = name;
    document.getElementById("reschedule-date").value = date;
    document.getElementById("reschedule-time").value = time;
    document.getElementById("rescheduleModal").showModal();
};

window.submitReschedule = async function () {
    const id = document.getElementById("reschedule-appointment-id").value;
    const date = document.getElementById("reschedule-date").value;
    const time = document.getElementById("reschedule-time").value;
    const btn = document.getElementById("btn-submit-reschedule");
    
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> Guardando...';

    try {
        const token = localStorage.getItem("access_token");
        const response = await fetch(`/api/appointments/${id}/reschedule`, {
            method: 'PATCH',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ appointment_date: date, appointment_time: time })
        });

        if (response.ok) {
            window.showToast("Cita reprogramada con éxito. Se ha enviado una notificación al cliente.", "success");
            document.getElementById("rescheduleModal").close();
            fetchDashboardData();
        } else {
            const errData = await response.json();
            window.showToast(errData.detail || "Error al reprogramar cita.", "error");
        }
    } catch (e) {
        console.error("Error al reprogramar:", e);
        window.showToast("Error de conexión al reprogramar la cita.", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
};

// --- Workflow de Auditoría y Revisión de Documentos desde el Dashboard ---

/**
 * Abre el modal de auditoría con el contenido completo del documento.
 * @param {number} docId - ID del documento a auditar
 * @param {boolean} focusReject - Si true, enfoca automáticamente en el textarea para rechazo
 */
window.viewDocFromDashboard = async function (docId, focusReject = false) {
    const modal = document.getElementById('docReviewModal');
    const loader = document.getElementById('review-modal-loader');
    const content = document.getElementById('review-modal-content');
    const docIdInput = document.getElementById('review-modal-doc-id');
    
    if (!modal) return;

    // Guardar el ID del documento en el input oculto
    docIdInput.value = docId;

    // Mostrar loader, ocultar contenido previo
    loader.classList.remove('hidden');
    content.classList.add('hidden');

    // Abrir el modal
    modal.showModal();

    const token = localStorage.getItem('access_token');
    try {
        const res = await fetch(`/api/documents/${docId}`, {
            headers: { 'Authorization': 'Bearer ' + token }
        });

        if (!res.ok) {
            const err = await res.json();
            window.showToast('Error al cargar documento: ' + (err.detail || 'Desconocido'), 'error');
            modal.close();
            return;
        }

        const doc = await res.json();

        // Rellenar los campos del modal con los datos del documento
        document.getElementById('review-modal-filename').textContent = doc.filename;
        document.getElementById('review-modal-author').textContent = doc.author_name || 'Propietario (ID: ' + doc.user_id + ')';
        document.getElementById('review-modal-date').textContent = new Date(doc.upload_date).toLocaleString('es-CO');
        document.getElementById('review-modal-text').textContent = doc.content_text || 'Sin contenido disponible.';
        document.getElementById('review-modal-id').textContent = '#' + doc.id;
        document.getElementById('review-modal-user-id').textContent = doc.user_id;
        document.getElementById('review-modal-chars').textContent = (doc.content_text || '').length.toLocaleString();

        // Estado visual
        const statusMap = {
            'draft': { label: 'Borrador', class: 'badge-ghost' },
            'pending_approval': { label: 'Pendiente', class: 'badge-warning' },
            'approved': { label: 'Aprobado', class: 'badge-success' },
            'rejected': { label: 'Rechazado', class: 'badge-error' },
            'signed': { label: 'Firmado', class: 'badge-info' }
        };
        const statusInfo = statusMap[doc.status] || { label: doc.status, class: 'badge-neutral' };
        const statusBadge = document.getElementById('review-modal-status-badge');
        statusBadge.textContent = statusInfo.label;
        statusBadge.className = 'badge badge-sm ' + statusInfo.class;
        document.getElementById('review-modal-status-text').textContent = statusInfo.label;

        // Comentarios previos
        const prevCommentsDiv = document.getElementById('review-modal-existing-comments');
        if (doc.comments) {
            document.getElementById('review-modal-prev-comments').textContent = doc.comments;
            prevCommentsDiv.classList.remove('hidden');
        } else {
            prevCommentsDiv.classList.add('hidden');
        }

        // Limpiar el textarea de nuevos comentarios
        document.getElementById('review-modal-comments').value = '';

        // Mostrar contenido, ocultar loader
        loader.classList.add('hidden');
        content.classList.remove('hidden');

        // Si se solicitó enfoque en rechazo, enfocar el textarea
        if (focusReject) {
            setTimeout(() => {
                const textarea = document.getElementById('review-modal-comments');
                textarea.focus();
                textarea.placeholder = '⚠️ OBLIGATORIO: Escriba los motivos del rechazo del documento...';
            }, 300);
        }

    } catch (e) {
        console.error('Error al cargar documento para auditoría:', e);
        window.showToast('Error de conexión al cargar el documento.', 'error');
        modal.close();
    }
};

/**
 * Envía la revisión (aprobar/rechazar) desde el modal de auditoría.
 * @param {string} action - 'approve' o 'reject'
 */
window.submitReviewFromModal = async function (action) {
    const docId = document.getElementById('review-modal-doc-id').value;
    const comments = document.getElementById('review-modal-comments').value.trim();
    const modal = document.getElementById('docReviewModal');

    if (!docId) {
        window.showToast('Error interno: no se encontró el ID del documento.', 'error');
        return;
    }

    // Validar comentarios obligatorios para rechazo
    if (action === 'reject' && !comments) {
        window.showToast('Debe incluir obligatoriamente los motivos del rechazo.', 'warning');
        document.getElementById('review-modal-comments').focus();
        document.getElementById('review-modal-comments').classList.add('textarea-error');
        setTimeout(() => document.getElementById('review-modal-comments').classList.remove('textarea-error'), 2000);
        return;
    }

    // Deshabilitar botones durante la petición
    const approveBtn = document.getElementById('review-modal-approve-btn');
    const rejectBtn = document.getElementById('review-modal-reject-btn');
    const originalApprove = approveBtn.innerHTML;
    const originalReject = rejectBtn.innerHTML;

    if (action === 'approve') {
        approveBtn.disabled = true;
        approveBtn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> Aprobando...';
    } else {
        rejectBtn.disabled = true;
        rejectBtn.innerHTML = '<span class="loading loading-spinner loading-xs"></span> Rechazando...';
    }

    const token = localStorage.getItem('access_token');
    try {
        const res = await fetch(`/api/documents/${docId}/review`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                action: action, 
                comments: comments || null 
            })
        });

        if (res.ok) {
            const actionLabel = action === 'approve' ? 'aprobado' : 'rechazado';
            window.showToast(`Documento ${actionLabel} exitosamente.`, action === 'approve' ? 'success' : 'info');
            modal.close();
            // Refrescar el dashboard completo para actualizar contadores y lista
            fetchDashboardData();
        } else {
            const err = await res.json();
            window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
        }
    } catch (e) {
        console.error('Error en revisión de documento:', e);
        window.showToast('Error de conexión al enviar la revisión.', 'error');
    } finally {
        approveBtn.disabled = false;
        rejectBtn.disabled = false;
        approveBtn.innerHTML = originalApprove;
        rejectBtn.innerHTML = originalReject;
    }
};

/**
 * Aprobación rápida directa desde la bandeja (sin abrir el modal).
 * Para casos donde el admin ya conoce el documento y quiere aprobar rápidamente.
 * @param {number} docId - ID del documento a aprobar
 */
window.quickApproveDoc = async function (docId) {
    if (!confirm('¿Desea aprobar este documento sin revisión detallada?')) return;

    const token = localStorage.getItem('access_token');
    try {
        const res = await fetch(`/api/documents/${docId}/review`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'approve' })
        });
        if (res.ok) {
            window.showToast('Contrato aprobado exitosamente.', 'success');
            fetchDashboardData();
        } else {
            const err = await res.json();
            window.showToast('Error: ' + (err.detail || 'Desconocido'), 'error');
        }
    } catch (e) {
        console.error(e);
        window.showToast('Error de conexión.', 'error');
    }
};

window.approveTemplateFromDashboard = async function (id) {
    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/templates/${id}/review`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'approve' })
        });
        if (res.ok) {
            window.showToast("Plantilla aprobada exitosamente.", "success");
            fetchDashboardData();
        } else {
            const err = await res.json();
            window.showToast("Error: " + (err.detail || "Desconocido"), "error");
        }
    } catch (e) {
        console.error(e);
        window.showToast("Error de conexión.", "error");
    }
};

window.rejectTemplateFromDashboard = async function (id) {
    const comments = prompt("Ingrese los motivos del rechazo de la plantilla:");
    if (comments === null) return;
    if (!comments.trim()) {
        window.showToast("Debe especificar un motivo para el rechazo.", "warning");
        return;
    }
    const token = localStorage.getItem("access_token");
    try {
        const res = await fetch(`/api/templates/${id}/review`, {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ action: 'reject', comments })
        });
        if (res.ok) {
            window.showToast("Plantilla rechazada exitosamente.", "info");
            fetchDashboardData();
        } else {
            const err = await res.json();
            window.showToast("Error: " + (err.detail || "Desconocido"), "error");
        }
    } catch (e) {
        console.error(e);
        window.showToast("Error de conexión.", "error");
    }
};
