const commentBox = document.querySelector(".comments");

function displayComment() {
    let name = document.querySelector("#name-input").value;
    let comment = document.querySelector("#comment-input").value;
    let newComment = document.createElement("p");

    newComment.innerText = `${name}: ${comment}`;
    commentBox.appendChild(newComment);
}