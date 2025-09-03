document.addEventListener('DOMContentLoaded', function() {
    // --- Recherche dynamique ---
    const searchInput = document.querySelector('input[name="q"]');
    const mangasList = document.getElementById('mangas-list');

    // 🔥 Vérification des éléments essentiels
    if (!searchInput || !mangasList) {
        console.error("Élément de recherche ou liste des mangas introuvable.");
        return;
    }

    // ✅ Débouncing pour éviter les requêtes excessives
    let debounceTimeout;
    searchInput.addEventListener('keyup', function() {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
            fetch(`/search?q=${encodeURIComponent(searchInput.value)}`)
                .then(response => response.json())
                .then(data => updateSearchResults(data));
        }, 400); // Attente de 400ms avant requête
    });

    // 📌 Mise à jour de l'affichage des favoris
    function updateFavoriteButton(button, mangaName, favorites) {
        button.textContent = favorites.includes(mangaName) ? "Retirer des favoris ★" : "Favori ★";
        button.classList.toggle('is-favorite', favorites.includes(mangaName));
    }

    // 🔄 Mise à jour dynamique des résultats de recherche
    function updateSearchResults(data) {
        mangasList.innerHTML = "";
        let favorites = JSON.parse(localStorage.getItem('mangaFavorites') || '[]');

        if (data.length === 0) {
            mangasList.innerHTML = "<p class='no-results'>Aucun manga trouvé.</p>";
            return;
        }

        data.forEach(manga => {
            const li = document.createElement("li");
            li.classList.add('manga-item');

            const a = document.createElement("a");
            a.href = "/manga/" + encodeURIComponent(manga.name);
            a.classList.add('manga-link');

            if (manga.cover) {
                const img = document.createElement("img");
                img.src = manga.cover;
                img.alt = "Cover de " + manga.name;
                img.classList.add('manga-cover');
                a.appendChild(img);
            }

            const span = document.createElement("span");
            span.textContent = manga.name;
            span.classList.add('manga-title');
            a.appendChild(span);
            li.appendChild(a);

            if (manga.syllabus) {
                const syllabusP = document.createElement("p");
                syllabusP.textContent = manga.syllabus;
                syllabusP.className = "syllabus";
                li.appendChild(syllabusP);
            }

            const nbChapitres = document.createElement("span");
            nbChapitres.className = "nb-chapitres";
            nbChapitres.textContent = manga.nb_chapitres + " chapitres";
            li.appendChild(nbChapitres);

            const favButton = document.createElement("button");
            favButton.classList.add('nav-link', 'add-favorite-btn');
            favButton.dataset.mangaName = manga.name;
            updateFavoriteButton(favButton, manga.name, favorites);

            favButton.addEventListener("click", function() {
                if (favorites.includes(manga.name)) {
                    favorites = favorites.filter(fav => fav !== manga.name);
                } else {
                    favorites.push(manga.name);
                }
                localStorage.setItem('mangaFavorites', JSON.stringify(favorites));
                updateFavoriteButton(favButton, manga.name, favorites);
            });

            li.appendChild(favButton);
            mangasList.appendChild(li);
        });
    }
});