/**
 * =====================================================
 * STAR-DOC :: Controlador JS para Diff & Comparador IA
 * =====================================================
 */
document.addEventListener('alpine:init', () => {
    Alpine.data('diffViewer', () => ({
        isOpen: false,
        loading: false,
        hasResults: false,
        activeTab: 'diff', // diff | analysis
        
        fileA: null,
        fileB: null,
        
        results: {
            filenames: { original: '', modified: '' },
            html_diff: '',
            analysis: {
                resumen_cambios: '',
                evaluacion_riesgo: '',
                nivel_riesgo: 'Bajo',
                modificaciones_detectadas: [],
                recomendaciones: []
            }
        },

        openModal(data = null) {
            this.isOpen = true;
            this.reset();
            
            // Si el modal se abre con datos preestablecidos (ej. desde el chat)
            if (data && data.html_diff && data.analysis) {
                this.results = data;
                this.hasResults = true;
                this.activeTab = 'analysis';
            }
        },

        closeModal() {
            this.isOpen = false;
            this.reset();
        },

        handleFileA(event) {
            const file = event.target.files[0];
            if (file) {
                this.fileA = file;
            }
        },

        handleFileB(event) {
            const file = event.target.files[0];
            if (file) {
                this.fileB = file;
            }
        },

        async runComparison() {
            if (!this.fileA || !this.fileB) {
                if (window.showToast) showToast('Por favor seleccione ambos archivos (Versión A y Versión B).', 'warning');
                else alert('Por favor seleccione ambos archivos (Versión A y Versión B).');
                return;
            }

            this.loading = true;
            this.hasResults = false;

            const formData = new FormData();
            formData.append("file_a", this.fileA);
            formData.append("file_b", this.fileB);

            try {
                // El token JWT para la autorización se obtiene del localStorage/cookie de la app
                // En STAR-DOC usualmente está en las cookies o podemos hacer la petición directa
                const response = await fetch('/comparison/compare-documents', {
                    method: 'POST',
                    body: formData,
                    // FastAPI automáticamente valida la sesión si la cookie está presente,
                    // de lo contrario intentará buscar los headers.
                });

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || "Error en la comparación de documentos.");
                }

                const data = await response.json();
                this.results = data;
                this.hasResults = true;
                this.activeTab = 'diff'; // Iniciar mostrando las diferencias visuales
            } catch (error) {
                console.error('Error ejecutando comparación Diff IA:', error);
                if (window.showToast) showToast('Error al realizar la comparación: ' + error.message, 'error');
                else alert('Error al realizar la comparación: ' + error.message);
                this.reset();
            } finally {
                this.loading = false;
            }
        },

        reset() {
            this.fileA = null;
            this.fileB = null;
            this.hasResults = false;
            this.loading = false;
            this.activeTab = 'diff';
            this.results = {
                filenames: { original: '', modified: '' },
                html_diff: '',
                analysis: {
                    resumen_cambios: '',
                    evaluacion_riesgo: '',
                    nivel_riesgo: 'Bajo',
                    modificaciones_detectadas: [],
                    recomendaciones: []
                }
            };
        }
    }));
});
