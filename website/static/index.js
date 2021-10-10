function deleteNote(noteId) {
    fetch('/delete-note', {
        // send note rewuest to delete note end point
        method: 'POST',
        body: JSON.stringify({noteId: noteId}),
    }).then((_res) => {
        // reload after getting response to show the home page with the delted note
            window.location.href = '/'
        })
}

function openNotification() {
    var notification = document.getElementById("notifications");
    if (notification.style.display === "none") {
      notification.style.display = "block";
    } else if(notification.style.display==="block"){
        notification.style.display='none'
    }else {
      notification.style.display = "block";
    }
  }
