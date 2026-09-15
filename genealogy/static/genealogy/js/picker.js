/* Alpine component for the searchable person selector (templates/includes/person_picker.html). */
window.personPicker = function (config) {
  return {
    query: config.label || "",
    selectedId: config.value || "",
    results: [],
    open: false,
    active: 0,
    async search() {
      this.selectedId = "";
      const q = this.query.trim();
      if (q.length < 2) {
        this.results = [];
        this.open = false;
        return;
      }
      try {
        const response = await fetch(`${config.endpoint}?q=${encodeURIComponent(q)}`, {
          headers: { Accept: "application/json" },
        });
        const data = await response.json();
        this.results = data.results.filter((p) => String(p.pk) !== String(config.exclude || ""));
        this.active = 0;
        this.open = true;
      } catch (error) {
        console.error("Person search failed", error);
      }
    },
    pick(person) {
      this.selectedId = person.pk;
      this.query = person.label;
      this.results = [];
      this.open = false;
    },
    move(step) {
      if (!this.results.length) return;
      this.open = true;
      this.active = (this.active + step + this.results.length) % this.results.length;
    },
    enter(event) {
      if (this.open && this.results[this.active]) {
        event.preventDefault();
        this.pick(this.results[this.active]);
      }
    },
  };
};
